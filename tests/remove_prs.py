import json
from github import Github
import os

if __name__ == "__main__":

    uat_file_path = "uat_new_collections.json"
    ops_file_path = "ops_new_collections.json"
    new_collection_titles = []

    with open(uat_file_path, "r") as json_file:
        data = json.load(json_file)
        for collection in data:
            concept_id = collection.get('concept_id')
            short_name = collection.get('short_name')
            title = f"UAT {concept_id} ({short_name})"
            new_collection_titles.append(title)

    with open(ops_file_path, "r") as json_file:
        data = json.load(json_file)
        for collection in data:
            concept_id = collection.get('concept_id')
            short_name = collection.get('short_name')
            title = f"UAT {concept_id} ({short_name})"
            new_collection_titles.append(title)

    # Replace these variables with your own values
    repo_owner = 'podaac'
    repo_name = 'l2ss-py-autotest'
    github_token = os.getenv("GITHUB_TOKEN")

    # Initialize a Github instance
    g = Github(github_token)

    # Get the repository
    repo = g.get_repo(f"{repo_owner}/{repo_name}")

    # Get all open pull requests
    open_pulls = repo.get_pulls(state='open')

    # Print each open pull request title and URL
    for pull in open_pulls:
        if pull.title not in new_collection_titles:
            # Close the pull request
            pull.edit(state='closed')
            print(f"Pull Request #{pull.number}: {pull.title} have been closed")
            print()
