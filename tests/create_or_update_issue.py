import os
import requests
import json
from datetime import datetime
from groq import Groq
import time
from requests.auth import HTTPBasicAuth


def bearer_token(env):
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

def summarize_error(client, error_message):

    content = f"summarize a descriptive error message in 10 words with only summary in response {error_message}"

    chat_completion = client.chat.completions.create(
        messages=[
            {
                "role": "user",
                "content": content
            }
        ],
        model="llama-3.2-3b-preview",
        temperature=0
    )

    result = chat_completion.choices[0].message.content
    return result


def create_or_update_issue(repo_name, github_token, env, groq_api_key):

    client = Groq(
        api_key=groq_api_key,
    )

    upper_env = env.upper()
    issue_title = f"Regression test for {upper_env} ISSUES"

    results_file = f'{env}_regression_results.json'
  
    with open(results_file, 'r') as file:
        test_results = json.load(file)

    current_associations_file = f'{env}_associations.json'

    with open(current_associations_file, 'r') as file:
        current_associations = json.load(file)
    
    failed = test_results.get('failed', [])
    failed_concept_ids = [collection.get('concept_id') for collection in failed]

    no_associations = []
    failed_test = []

    for collection_concept_id in failed_concept_ids: 
        if collection_concept_id not in current_associations:
            no_associations.append(collection_concept_id)
        else:
            failed_test.append(collection_concept_id)

    unique_no_associations = list(set(no_associations))
    providers = []
    issue_body = None

    all_collections = failed_concept_ids

    if len(failed) > 0:

        for collection in failed_concept_ids:
            provider = collection.split('-')[1]
            if provider not in providers:
                providers.append(provider)

        for item in failed:
            message = item.get('message')
            try:
                error_message = summarize_error(client, message)
            except Exception:
                error_message = "Unable to retrieve an error message"
            item['error_message'] = error_message

            time.sleep(10)

        collection_names = get_collection_names(providers, env, all_collections)
        issue_body = datetime.now().strftime("Updated on %m-%d-%Y\n")

        if len(failed_test) > 0:
            issue_body += "\n FAILED: \n"
            issue_body += "\n".join(f"{cid.get('concept_id')} ({collection_names.get(cid.get('concept_id'), '')}) - {cid.get('test_type')} test -  {cid.get('error_message')}" for cid in failed)
        if len(unique_no_associations) > 0:
            issue_body += "\n NO ASSOCIATIONS: \n"
            issue_body += "\n".join(f"{cid} ({collection_names.get(cid, '')})" for cid in unique_no_associations)

    else:
        issue_body = "There are no failed collections"

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
    groq_api_key = os.getenv("GROQ_API_KEY")

    # Call the create_or_update_issue function with repository and token
    create_or_update_issue(repo_name, github_token, env, groq_api_key)
