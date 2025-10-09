import glob
import json
import os
import requests
import time


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


def main():
    job_status_files = glob.glob(os.path.join('job-status', '*', 'job_status.json'))
    failed = False
    repo = os.environ.get('GITHUB_REPOSITORY')
    token = os.environ.get('GITHUB_TOKEN')
    for fpath in job_status_files:
        with open(fpath) as f:
            data = json.load(f)
        if data.get('status') != 'success':
            url = data.get('url', '')
            reason = data.get('reason', '')
            print(f"FAILED JOB: {url}")
            print("REGRESSION RESULTS:")
            try:
                # Pretty print the JSON if possible
                reason_json = json.loads(reason)
                pretty_reason = json.dumps(reason_json, indent=2)
            except Exception:
                pretty_reason = reason
            print(pretty_reason)
            print("----------------------")
            failed = True
            # Create or update GitHub issue if repo and token are available
            if repo and token:
                title = f"Regression Failure: {data.get('env', '')} {data.get('file', '')}"
                body = f"Job URL: {url}\n\nRegression Results:\n```json\n{pretty_reason}\n```"
                create_or_update_github_issue(repo, token, title, body, labels=["regression-failure"])
    if not failed:
        print("No failed jobs.")

if __name__ == "__main__":
    main()
