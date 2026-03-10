import json
import os

import boto3
import requests
from requests.auth import HTTPBasicAuth


def get_bearer_token_via_lambda(
    lambda_function_name,
    edl_user,
    edl_pass,
    cmr_env,
    client_id="l2sspyautotestgithubaction",
    aws_region="us-west-2",
):
    payload = {
        "client_id": client_id,
        "edl_user": edl_user,
        "edl_pass": edl_pass,
        "cmr_env": cmr_env,
        "action": "edl",
    }

    lambda_client = boto3.client("lambda", region_name=aws_region)
    response = lambda_client.invoke(
        FunctionName=lambda_function_name,
        Payload=json.dumps(payload),
    )

    result_payload = response["Payload"].read()
    result_json = json.loads(result_payload)

    if "errorMessage" in result_json:
        raise Exception(f"Lambda error: {result_json['errorMessage']}")
    if "access_token" not in result_json:
        raise Exception("No token found in Lambda response")

    return result_json["access_token"]


def fetch_bearer_token(env, request_session=None, cmr_user=None, cmr_pass=None):
    token = os.environ.get("CMR_BEARER_TOKEN")
    if token:
        return token

    env = env.lower()
    url = f"https://{'uat.' if env == 'uat' else ''}urs.earthdata.nasa.gov/api/users/find_or_create_token"

    user = cmr_user or os.environ.get("CMR_USER")
    pwd = cmr_pass or os.environ.get("CMR_PASS")
    if not user or not pwd:
        raise RuntimeError("CMR_USER and CMR_PASS are required to fetch a bearer token")

    session = request_session or requests.Session()
    resp = session.post(url, auth=HTTPBasicAuth(user, pwd))
    if resp.status_code == 200:
        response_content = resp.json()
        access_token = response_content.get("access_token")
        if access_token:
            return access_token

    raise RuntimeError(f"Error getting token (status code {resp.status_code})")


def fetch_bearer_token_by_provider(env, token_provider, request_session=None):
    env = env.lower()
    if token_provider == "lambda":
        lambda_function_name = os.environ.get(
            "CMR_TOKEN_LAMBDA_FUNCTION_NAME", "uat-launchpad_token_dispenser"
        )
        return get_bearer_token_via_lambda(
            lambda_function_name=lambda_function_name,
            edl_user=os.environ["CMR_USER"],
            edl_pass=os.environ["CMR_PASS"],
            cmr_env=env,
            client_id=os.environ.get(
                "CMR_TOKEN_CLIENT_ID", f"l2sspyautotestgithubaction{env}"
            ),
            aws_region=os.environ.get("CMR_TOKEN_LAMBDA_REGION", "us-west-2"),
        )

    return fetch_bearer_token(env, request_session=request_session)
