import os
import requests
import json
from datetime import datetime

def bearer_token(env):
    tokens = []
    headers: dict = {'Accept': 'application/json'}
    url: str = f"https://{'uat.' if env == 'uat' else ''}urs.earthdata.nasa.gov/api/users"

    # First just try to get a token that already exists
    try:
        resp = requests.get(url + "/tokens", headers=headers,
                                   auth=requests.auth.HTTPBasicAuth(os.environ['CMR_USER'], os.environ['CMR_PASS']))
        response_content = json.loads(resp.content)

        for x in response_content:
            tokens.append(x['access_token'])

    except Exception as ex:  # noqa E722
        print(ex)
        print("Error getting the token - check user name and password")

    # No tokens exist, try to create one
    if not tokens:
        try:
            resp = requests.post(url + "/token", headers=headers,
                                        auth=requests.auth.HTTPBasicAuth(os.environ['CMR_USER'], os.environ['CMR_PASS']))
            response_content: dict = json.loads(resp.content)
            tokens.append(response_content['access_token'])
        except Exception as ex:  # noqa E722
            print(ex)
            print("Error getting the token - check user name and password")

    # If still no token, then we can't do anything
    if not tokens:
        return None

    return next(iter(tokens))


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
                print(response)
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


def get_existing_issue_number(repo_name, issue_title, github_token):
    url = f"https://api.github.com/repos/{repo_name}/issues"

    headers = {
        'Authorization': f'token {github_token}',
        'Accept': 'application/vnd.github.v3+json'
    }

    response = requests.get(url, headers=headers)
    response.raise_for_status()

    issues = response.json()

    for issue in issues:
        if issue['title'] == issue_title:
            return issue['number']

    return None


def create_issue(repo_name, issue_title, issue_body, github_token):
    url = f"https://api.github.com/repos/{repo_name}/issues"

    headers = {
        'Authorization': f'token {github_token}',
        'Accept': 'application/vnd.github.v3+json'
    }

    payload = {
        'title': issue_title,
        'body': issue_body
    }

    response = requests.post(url, headers=headers, json=payload)
    response.raise_for_status()

    print(f"Issue created successfully: {response.json()['html_url']}")


def update_issue(repo_name, issue_number, issue_body, github_token):
    url = f"https://api.github.com/repos/{repo_name}/issues/{issue_number}"

    headers = {
        'Authorization': f'token {github_token}',
        'Accept': 'application/vnd.github.v3+json'
    }

    payload = {
        'body': issue_body
    }

    response = requests.patch(url, headers=headers, json=payload)
    response.raise_for_status()

    print(f"Issue updated successfully: {response.json()['html_url']}")


def create_or_update_issue(repo_name, github_token, env):

    upper_env = env.upper()
    issue_title = f"Regression test for {upper_env} ISSUES"

    results_file = f'{env}_regression_results.json'
    with open(results_file, 'r') as file:
        # Load the JSON data from the file
        results = json.load(file)

    failed = results.get('failed', [])
    skipped = results.get('skipped',[])

    providers = []
    issue_body = None

    all_collections = failed + skipped

    if len(failed) > 0 or len(skipped) > 0:

        for collection in failed:
            provider = collection.split('-')[1]
            if provider not in providers:
                providers.append(provider)
        for collection in skipped:
            provider = collection.split('-')[1]
            if provider not in providers:
                providers.append(provider)

        collection_names = get_collection_names(providers, env, all_collections)
        issue_body = datetime.now().strftime("Updated on %m-%d-%Y\n")

        if len(failed) > 0:
            issue_body += "\n FAILED: \n"
            issue_body += "\n".join(f"{cid} ({collection_names.get(cid, '')})" for cid in failed)
        if len(skipped) > 0:
            issue_body += "\n SKIPPED: \n"
            issue_body += "\n".join(f"{cid} ({collection_names.get(cid, '')})" for cid in skipped)

    else:
        issue_body = "There are no failed or skipped collections"

    existing_issue_number = get_existing_issue_number(
        repo_name, issue_title, github_token)

    if existing_issue_number:
        # Update the existing issue
        update_issue(repo_name, existing_issue_number,
                     issue_body, github_token)
    else:
        # Create a new issue
        create_issue(repo_name, issue_title, issue_body, github_token)


if __name__ == "__main__":
    # Get repository and token from environment variables
    repo_name = os.getenv("GITHUB_REPOSITORY")
    github_token = os.getenv("GITHUB_TOKEN")
    env = os.getenv("ENV")

    # Call the create_or_update_issue function with repository and token
    create_or_update_issue(repo_name, github_token, env)
