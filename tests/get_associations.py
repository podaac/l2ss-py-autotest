import os
import requests
import json
from datetime import datetime
import cmr

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

def get_associations(token, env):

    mode = cmr.queries.CMR_UAT
    if env == "ops":
        mode = cmr.queries.CMR_OPS

    headers = {
        "Authorization": f"Bearer {token}"
    }

    service_concept_id = cmr.queries.ServiceQuery(mode=mode).provider('POCLOUD').name('PODAAC L2 Cloud Subsetter').get()[0].get('concept_id')
    url = cmr.queries.CollectionQuery(mode=mode).service_concept_id(service_concept_id)._build_url()
    collections_query = requests.get(url, headers=headers, params={'page_size': 2000}).json()['feed']['entry']
    collections = [a.get('id') for a in collections_query]

    filename = f"{env}_associations.json"
    with open(filename, 'w') as file:
        json.dump(collections, file)


if __name__ == "__main__":
    # Get repository and token from environment variables

    env = os.getenv("ENV")
    token = bearer_token(env)
    get_associations(token, env)
