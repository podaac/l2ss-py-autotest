import glob
import json
import os
import requests
import time
import boto3
import re
from requests.auth import HTTPBasicAuth
import textwrap
from botocore.config import Config
from datetime import datetime
from podaac_agents.agents.stack_trace_agent import stack_trace_agent

def bearer_token(env):

    # Try to get token from environment variable first
    token = os.environ.get("CMR_BEARER_TOKEN")
    if token:
        return token

    env = env.lower()
    url = f"https://{'uat.' if env == 'uat' else ''}urs.earthdata.nasa.gov/api/users/find_or_create_token"

    try:
        # Make the request with the Base64-encoded Authorization header
        resp = requests.post(
            url,
            auth=HTTPBasicAuth(os.environ['CMR_USER'], os.environ['CMR_PASS'])
        )

        # Check for successful response
        if resp.status_code == 200:
            response_content = resp.json()
            return response_content.get('access_token')

    except Exception as e:
        status_code = resp.status_code if 'resp' in locals() and resp else "N/A"
        print(f"Error getting the token (status code {status_code}): {e}")


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


def get_github_issue_by_title(repo, token, title, max_retries=5, delay=2):
    url = f"https://api.github.com/repos/{repo}/issues"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github+json"
    }
    # Search both open and closed issues
    for state in ["open", "closed"]:
        params = {"state": state, "per_page": 100}
        for attempt in range(1, max_retries + 1):
            try:
                response = requests.get(url, headers=headers, params=params, timeout=10)
                if response.status_code == 200:
                    issues = response.json()
                    for issue in issues:
                        if issue.get("title") == title:
                            # If closed, reopen it
                            if issue.get("state") == "closed":
                                issue_number = issue["number"]
                                reopen_url = f"https://api.github.com/repos/{repo}/issues/{issue_number}"
                                reopen_data = {"state": "open"}
                                reopen_resp = requests.patch(reopen_url, headers=headers, json=reopen_data)
                                if reopen_resp.status_code == 200:
                                    print(f"Reopened closed issue: {title}")
                                else:
                                    print(f"Failed to reopen issue: {title} (status {reopen_resp.status_code})\n{reopen_resp.text}")
                                # Refresh issue data after reopening
                                response2 = requests.get(reopen_url, headers=headers)
                                if response2.status_code == 200:
                                    return response2.json()
                                else:
                                    return issue
                            return issue
                    # If not found, wait and retry
                    if attempt < max_retries:
                        print(f"Issue with title '{title}' not found in state '{state}', retrying ({attempt}/{max_retries})...")
                        time.sleep(delay)
                else:
                    print(f"Failed to fetch issues (attempt {attempt}, state {state}): {response.status_code}\n{response.text}")
            except Exception as e:
                print(f"Exception fetching issues (attempt {attempt}, state {state}): {e}")
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

    # return "test summary"
    model_id="openai.gpt-oss-120b-1:0"
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

    raw_answer = result["choices"][0]["message"]["content"]
    # Remove any <reasoning>…</reasoning> block
    clean_answer = re.sub(r"<reasoning>.*?</reasoning>", "", raw_answer, flags=re.DOTALL).strip()
    # Keep only the first non-empty line
    clean_answer = clean_answer.splitlines()[0]
    return clean_answer

def bedrock_summarize_error_anthropic(runtime, error_message):

    model_id = "us.anthropic.claude-haiku-4-5-20251001-v1:0"

    prompt = (
        "Summarize the following error message in exactly 10 words. "
        "Output ONLY the 10-word summary as plain text. "
        "Do not include reasoning, explanations, tags, or extra text. "
        f"Error message: {error_message}"
    )

    response = runtime.invoke_model(
        modelId=model_id,
        body=json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 100,
            "temperature": 0,
            "messages": [
                {"role": "user", "content": [{"type": "text", "text": prompt}]}
            ]
        })
    )

    result = json.loads(response["body"].read())

    # Claude responses in Bedrock put text here:
    raw_answer = result["content"][0]["text"]

    # Remove any <reasoning>…</reasoning> tags (Claude sometimes adds them)
    clean_answer = re.sub(r"<reasoning>.*?</reasoning>", "", raw_answer, flags=re.DOTALL).strip()
    clean_answer = clean_answer.splitlines()[0]
    return clean_answer


def bedrock_suggest_solution(runtime, error_message):

    # return "test solution"
    model_id="openai.gpt-oss-120b-1:0"
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


def bedrock_suggest_solution_anthropic(runtime, error_message):

    model_id = "us.anthropic.claude-haiku-4-5-20251001-v1:0"

    prompt = (
        "Given the following error message, suggest a possible solution or next step. "
        "Output ONLY the solution as plain text. "
        "Do not include reasoning, explanations, tags, or extra text. "
        f"Error message: {error_message}"
    )

    response = runtime.invoke_model(
        modelId=model_id,
        body=json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 100,
            "temperature": 0,
            "messages": [
                {"role": "user", "content": [{"type": "text", "text": prompt}]}
            ]
        })
    )

    result = json.loads(response["body"].read())

    # Claude responses in Bedrock put text here:
    raw_answer = result["content"][0]["text"]

    # Remove any <reasoning>…</reasoning> tags (Claude sometimes adds them)
    clean_answer = re.sub(r"<reasoning>.*?</reasoning>", "", raw_answer, flags=re.DOTALL).strip()
    clean_answer = clean_answer.splitlines()[0]
    return clean_answer


def create_aggregated_github_issue(repo, token, all_failures, env, collection_names):
    title = f"Aggregated Regression Failures {env}"
    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")

    body_lines = [
        f"**Updated:** {timestamp}\n",
        f"# Aggregated Regression Failures\n",
    ]

    for fail in all_failures:
        concept_id = fail.get('concept_id', '')
        job_url = fail.get('job_url', '')
        issue_url = fail.get('issue_url', '')
        test_type = fail.get('test_type', '')
        summary = fail.get('summary', '')
        short_name = collection_names.get(concept_id, 'Unknown Collection')
        # Ensure links are valid URLs or empty
        job_url_str = f"[regression]({job_url})" if job_url and job_url.startswith('http') else ''
        issue_url_str = f"[issue]({issue_url})" if issue_url and issue_url.startswith('http') else ''
        line = f"- `{concept_id}` ({short_name}) -- {test_type} -- {issue_url_str} {summary}".strip()
        body_lines.append(line)
    body = "\n".join(body_lines)
    create_or_update_github_issue(repo, token, title, body, labels=["regression-aggregated"])


def get_all_regression_failure_issues(repo, token, label, state="open", max_pages=10):
    """
    Fetch all issues with the label 'regression-failure' from the given repo.
    :param repo: GitHub repo in 'owner/repo' format
    :param token: GitHub token
    :param state: 'open', 'closed', or 'all' (default)
    :param max_pages: Max number of pages to fetch (pagination)
    :return: List of issues with the label 'regression-failure'
    """
    url = f"https://api.github.com/repos/{repo}/issues"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github+json"
    }
    issues = []
    page = 1
    while page <= max_pages:
        params = {
            "state": state,
            "labels": label,
            "per_page": 100,
            "page": page
        }
        response = requests.get(url, headers=headers, params=params, timeout=10)
        if response.status_code == 200:
            page_issues = response.json()
            if not page_issues:
                break
            issues.extend(page_issues)
            if len(page_issues) < 100:
                break  # Last page
            page += 1
        else:
            print(f"Failed to fetch regression-failure issues (page {page}): {response.status_code}\n{response.text}")
            break
    return issues


def get_collection_names(providers, env, collections_list):

    lower_env = env.lower()

    if lower_env == "uat":
        url = "https://graphql.uat.earthdata.nasa.gov/api"
    elif lower_env == "ops":
        url = "https://graphql.earthdata.nasa.gov/api"

    token = bearer_token(env)

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}"
    }

    # Get providers
    collections = {}

    for provider in providers:

        offset = 0
        more_data = True
        while more_data:

            try:

                # Define your GraphQL query
                graphql_query_template = """
                    query {{
                      collections(provider: "{provider}", limit: 2000, offset: {offset}) {{
                        items {{
                          conceptId
                          shortName
                        }}
                      }}
                    }}
                """

                graphql_query = graphql_query_template.format(
                    provider=provider, offset=offset)

                # Create the request payload
                payload = {"query": graphql_query}

                # Make the GraphQL request with headers
                response = requests.post(url, headers=headers, json=payload)
                # Check the status code
                if response.status_code == 200:
                    # Parse the JSON response
                    data = response.json().get('data').get('collections').get('items')

                    for item in data:
                        concept_id = item.get('conceptId')
                        if concept_id in collections_list:
                            collections[concept_id] = item.get("shortName")

                    if len(data) < 2000:
                        more_data = False
                    else:
                        offset += 2000
                else:
                    more_data = False
                    print(f"Error: {response.status_code}\n{response.text}")

            except Exception as ex:
                print(f"Error: {ex}")
                more_data = False

    return collections


def main():
    job_status_files = glob.glob(os.path.join('job-status', '*', 'job_status.json'))
    failed = False
    repo = os.environ.get('GITHUB_REPOSITORY')
    token = os.environ.get('GITHUB_TOKEN')
    env = os.environ.get('REGRESSION_ENV', 'uat')
    label = f"regression-failure-{env}"

    collection_concept_id = []
    providers = []

    # First pass: Collect concept IDs and providers
    for fpath in job_status_files:
        with open(fpath) as f:
            data = json.load(f)
        if data.get('status') != 'success':
            reason = data.get('reason', '')
            try:
                reason_json = json.loads(reason)
                if isinstance(reason_json, dict) and "failed" in reason_json:
                    for fail in reason_json["failed"]:
                        concept_id = fail.get('concept_id', '')
                        if concept_id and concept_id not in collection_concept_id:
                            collection_concept_id.append(concept_id)
                            # Get provider from concept_id (assuming the format stays the same)
                            provider = concept_id.split('-')[1]
                            if provider not in providers:
                                providers.append(provider)
            except Exception:
                pass

    collection_names = get_collection_names(providers, env, collection_concept_id)  

    retry_config = Config(
        retries={
            "max_attempts": 10,
            "mode": "adaptive"
        }
    )

    runtime = boto3.client(service_name="bedrock-runtime", region_name="us-west-2", config=retry_config)

    old_issues = get_all_regression_failure_issues(repo, token, label)
    old_issue_numbers = [issue["number"] for issue in old_issues]

    all_failures = []
    failure_issue_numbers = []
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
                timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")

                if isinstance(reason_json, dict) and "failed" in reason_json:
                    error_sections = []
                    for fail in reason_json["failed"]:
                        fail["message"] = format_message(fail["message"])
                        #solution = bedrock_suggest_solution_anthropic(runtime, fail["message"])
                        #summary = bedrock_summarize_error_anthropic(runtime, fail["message"])

                        # Use the stack trace agent to get the solution and summary
                        response = stack_trace_agent(fail["message"])
                        
                        solution = response.structured_output.suggested_solution
                        short_summary = response.structured_output.short_summary
                        detailed_summary = response.structured_output.detailed_summary
                        wrapped_solution = "\n".join(textwrap.wrap(solution, width=100))

                        concept_id = fail.get('concept_id', '')
                        short_name = collection_names.get(concept_id, 'Unknown Collection')
                        test_type = fail.get('test_type', '')

                        # Create or update individual issue
                        section = (
                            f"### Concept ID: `{concept_id}` | Short Name: `{short_name}` | Test Type: `{test_type}`\n"
                            f"**Error Message:**\n"
                            f"```text\n{fail.get('message', '').strip()}\n```\n"
                            f"**Summary:**\n"
                            f"```text\n{detailed_summary}\n```\n"
                            f"**Suggested Solution:**\n"
                            f"```text\n{wrapped_solution}\n```\n"
                        )

                        error_sections.append(section)
                        issue_url = None
                        if repo and token:
                            title = f"Regression Failure: {env} | {concept_id} | {short_name}"
                            body_md = (
                                f"**Updated:** {timestamp}\n\n"
                                f"Job URL: {url}\n\n"
                                + section
                            )
                            issue = get_github_issue_by_title(repo, token, title)
                            if not issue:
                                create_github_issue(repo, token, title, body_md, labels=[label])
                                issue = get_github_issue_by_title(repo, token, title)
                            if issue:
                                issue_url = issue.get('html_url')
                                issue_number = issue.get('number')
                                if issue_number is not None:
                                    failure_issue_numbers.append(issue_number)

                        concept_id = fail.get('concept_id', '')
                        if concept_id not in collection_concept_id:
                            collection_concept_id.append(concept_id)
                        all_failures.append({
                            'concept_id': concept_id,
                            'test_type': fail.get('test_type', ''),
                            'message': fail.get('message', '').strip(),
                            'solution': solution,
                            'job_url': url,
                            'issue_url': issue_url,
                            'summary': short_summary
                        })
                    pretty_reason = json.dumps(reason_json, indent=2)
                    body_md = f"**Updated:** {timestamp}\n\nJob Run: {url}\n\nRegression Failures:\n\n" + "\n".join(error_sections)
                else:
                    pretty_reason = format_message(reason)
                    body_md = f"**Updated:** {timestamp}\n\nJob Run: {url}\n\nRegression Results:\n```text\n{pretty_reason}\n```"
            except Exception as ex:
                print(ex)
                pretty_reason = format_message(reason)
                body_md = f"**Updated:** {timestamp}\n\nJob Run: {url}\n\nRegression Results:\n```text\n{pretty_reason}\n```"
            print(pretty_reason)
            print("----------------------")
            failed = True
            if repo and token:
                short_name = collection_names.get(concept_id, 'Unknown Collection')
                title = f"Regression Failure: {env} | {concept_id} | {short_name}"
                create_or_update_github_issue(repo, token, title, body_md, labels=[label])

    for number in old_issue_numbers:
        if number not in failure_issue_numbers:
            url = f"https://api.github.com/repos/{repo}/issues/{number}"
            headers = {
                "Authorization": f"token {token}",
                "Accept": "application/vnd.github+json"
            }
            data = {"state": "closed"}
            response = requests.patch(url, headers=headers, json=data)
            if response.status_code == 200:
                print(f"Closed issue number: {number}")
            else:
                print(f"Failed to close issue number: {number} (status {response.status_code})\n{response.text}")

    if all_failures and repo and token:
        create_aggregated_github_issue(repo, token, all_failures, env, collection_names)
    if not failed:
        print("No failed jobs.")

if __name__ == "__main__":
    main()
