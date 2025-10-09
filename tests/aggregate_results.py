import glob
import json
import os
import requests
import time
import boto3
import re

def create_github_issue(repo, token, title, body, labels=None):
    url = f"https://api.github.com/repos/{repo}/issues"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github+json"
    }
    data = {
        "title": title,
        "body": body,
    }
    if labels:
        data["labels"] = labels
    response = requests.post(url, headers=headers, json=data)
    if response.status_code == 201:
        print(f"Created issue: {title}")
    else:
        print(f"Failed to create issue: {title} (status {response.status_code})\n{response.text}")


def get_github_issue_by_title(repo, token, title, max_retries=3, delay=2):
    url = f"https://api.github.com/repos/{repo}/issues"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github+json"
    }
    params = {"state": "open", "per_page": 100}
    for attempt in range(1, max_retries + 1):
        try:
            response = requests.get(url, headers=headers, params=params, timeout=10)
            if response.status_code == 200:
                issues = response.json()
                for issue in issues:
                    if issue.get("title") == title:
                        return issue
                return None
            else:
                print(f"Failed to fetch issues (attempt {attempt}): {response.status_code}\n{response.text}")
        except Exception as e:
            print(f"Exception fetching issues (attempt {attempt}): {e}")
        if attempt < max_retries:
            time.sleep(delay)
    return None


def create_or_update_github_issue(repo, token, title, body, labels=None):
    existing_issue = get_github_issue_by_title(repo, token, title)
    if existing_issue:
        issue_number = existing_issue["number"]
        url = f"https://api.github.com/repos/{repo}/issues/{issue_number}"
        headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github+json"
        }
        data = {"body": body}
        if labels:
            data["labels"] = labels
        response = requests.patch(url, headers=headers, json=data)
        if response.status_code == 200:
            print(f"Updated issue: {title}")
        else:
            print(f"Failed to update issue: {title} (status {response.status_code})\n{response.text}")
    else:
        create_github_issue(repo, token, title, body, labels)


def format_message(msg, max_lines=30):
    import re
    msg = msg.replace("\\n", "\n")
    msg = re.sub(r'<[^>]+>', '', msg)
    lines = msg.splitlines()
    if len(lines) > max_lines:
        lines = lines[:max_lines] + ['... (truncated) ...']
    return "\n".join(lines)


def bedrock_summarize_error(runtime, error_message):

    model_id = "openai.gpt-oss-120b-1:0"   # example
    prompt = (
        "Summarize the following error message in exactly 10 words. "
        "Output ONLY the 10-word summary as plain text. "
        "Do not include reasoning, explanations, tags, or extra text. "
        f"Error message: {error_message}"
    )

    response = runtime.invoke_model(
        modelId=model_id,
        body=json.dumps({
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 5000,
            "temperature": 0
        })
    )

    result = json.loads(response["body"].read())

    print(result)
    raw_answer = result["choices"][0]["message"]["content"]
    # Remove any <reasoning>…</reasoning> block
    clean_answer = re.sub(r"<reasoning>.*?</reasoning>", "", raw_answer, flags=re.DOTALL).strip()
    # Keep only the first non-empty line
    clean_answer = clean_answer.splitlines()[0]
    return clean_answer


def bedrock_suggest_solution(runtime, error_message):
    model_id = "openai.gpt-oss-120b-1:0"   # example
    prompt = (
        "Given the following error message, suggest a possible solution or next step. "
        "Output ONLY the solution as plain text. "
        "Do not include reasoning, explanations, tags, or extra text. "
        f"Error message: {error_message}"
    )
    response = runtime.invoke_model(
        modelId=model_id,
        body=json.dumps({
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 5000,
            "temperature": 0
        })
    )
    result = json.loads(response["body"].read())
    raw_answer = result["choices"][0]["message"]["content"]
    # Remove any <reasoning>…</reasoning> block
    clean_answer = re.sub(r"<reasoning>.*?</reasoning>", "", raw_answer, flags=re.DOTALL).strip()
    # Keep only the first non-empty line
    clean_answer = clean_answer.splitlines()[0]
    return clean_answer


def main():
    job_status_files = glob.glob(os.path.join('job-status', '*', 'job_status.json'))
    failed = False
    repo = os.environ.get('GITHUB_REPOSITORY')
    token = os.environ.get('GITHUB_TOKEN')

    runtime = boto3.client(service_name="bedrock-runtime", region_name="us-west-2")

    for fpath in job_status_files:
        with open(fpath) as f:
            data = json.load(f)
        if data.get('status') != 'success':
            url = data.get('url', '')
            reason = data.get('reason', '')
            print(f"FAILED JOB: {url}")
            print("REGRESSION RESULTS:")
            try:
                reason_json = json.loads(reason)
                # Format each failed message for better readability
                if isinstance(reason_json, dict) and "failed" in reason_json:
                    error_sections = []
                    for fail in reason_json["failed"]:
                        fail["message"] = format_message(fail["message"])
                        solution = bedrock_suggest_solution(runtime, fail["message"])
                        section = (
                            f"### Concept ID: `{fail.get('concept_id', '')}` | Test Type: `{fail.get('test_type', '')}`\n"
                            f"**Error Message:**\n"
                            f"```text\n{fail.get('message', '').strip()}\n```\n"
                            f"**Possible Solution:**\n"
                            f"```text\n{solution}\n```\n"
                        )
                        error_sections.append(section)
                    pretty_reason = json.dumps(reason_json, indent=2)
                    body_md = f"Job URL: {url}\n\nRegression Failures:\n\n" + "\n".join(error_sections)
                else:
                    pretty_reason = format_message(reason)
                    body_md = f"Job URL: {url}\n\nRegression Results:\n```text\n{pretty_reason}\n```"
            except Exception as ex:
                print(ex)
                pretty_reason = format_message(reason)
                body_md = f"Job URL: {url}\n\nRegression Results:\n```text\n{pretty_reason}\n```"
            print(pretty_reason)
            print("----------------------")
            failed = True
            # Create or update GitHub issue if repo and token are available
            if repo and token:
                title = f"Regression Failure: {data.get('env', '')} {data.get('file', '')}"
                create_or_update_github_issue(repo, token, title, body_md, labels=["regression-failure"])
    if not failed:
        print("No failed jobs.")

if __name__ == "__main__":
    main()
