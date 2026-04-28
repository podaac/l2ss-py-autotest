"""Creates, manages, and returns an Earthdata Login (EDL) Authorization Bearer Token.

Reads EDL_SERVICE_USERNAME and EDL_SERVICE_PASSWORD from OS environment variables.
Automatically revokes tokens expiring within 1 day and re-uses healthy tokens.

Documentation on tokens: https://urs.earthdata.nasa.gov/documentation/for_users/user_token
"""

import argparse
import os
import sys
from datetime import datetime, timedelta

import requests
from requests.auth import HTTPBasicAuth

HEADERS = {"Accept": "application/json"}

def get_and_clean_existing_tokens(username, password, tokens_url, delete_token_url):
    """
    Fetches existing tokens, and only deletes tokens expiring within a day
    when there are two or more such tokens. Returns a valid token if one exists.
    """
    get_response = requests.get(tokens_url, headers=HEADERS, auth=HTTPBasicAuth(username, password))
    
    # If the endpoint fails or returns no tokens, return None
    if get_response.status_code != 200:
        return None
        
    existing_tokens = get_response.json()
    if not isinstance(existing_tokens, list):
        return None

    valid_token = None
    expiring_soon_tokens = []
    now = datetime.now()
    one_day_from_now = now + timedelta(days=1)
    
    for token_info in existing_tokens:
        access_token = token_info.get("access_token")
        exp_date_str = token_info.get("expiration_date")
        
        if access_token and exp_date_str:
            try:
                # Parse the date format "MM/DD/YYYY"
                exp_date = datetime.strptime(exp_date_str, "%m/%d/%Y")
                
                if exp_date <= one_day_from_now:
                    expiring_soon_tokens.append(access_token)
                else:
                    # Save the first healthy token we find to return later
                    if not valid_token:
                        valid_token = access_token
                        
            except ValueError:
                pass

    if len(expiring_soon_tokens) >= 2:
        for access_token in expiring_soon_tokens:
            requests.post(
                f"{delete_token_url}={access_token}",
                headers=HEADERS,
                auth=HTTPBasicAuth(username, password),
            )
                
    return valid_token

def generate_edl_token(env):
    """
    Manages and returns an EDL bearer token for the specified environment.
    
    Args:
        env (str): The environment to generate the token for ('uat' or 'ops').
        
    Returns:
        str: The generated or retrieved bearer token, or None if the process fails.
    """
    env = env.lower()
    
    username = os.getenv("EDL_SERVICE_USERNAME") or os.getenv("EDL_USERNAME")
    password = os.getenv("EDL_SERVICE_PASSWORD") or os.getenv("EDL_PASSWORD")
    
    if not username or not password:
        print(
            "Error: EDL_SERVICE_USERNAME or EDL_SERVICE_PASSWORD environment variables are not set.",
            file=sys.stderr,
        )
        sys.exit(1)
    
    if env == "uat":
        token_url = "https://uat.urs.earthdata.nasa.gov/api/users/token"
        tokens_url = "https://uat.urs.earthdata.nasa.gov/api/users/tokens"
        delete_token_url = "https://uat.urs.earthdata.nasa.gov/api/users/revoke_token?token"
    elif env == "ops":
        token_url = "https://urs.earthdata.nasa.gov/api/users/token"
        tokens_url = "https://urs.earthdata.nasa.gov/api/users/tokens"
        delete_token_url = "https://urs.earthdata.nasa.gov/api/users/revoke_token?token"
    else:
        print("Error: Invalid environment. Please specify 'uat' or 'ops'.", file=sys.stderr)
        return None

    # Step 1: Clean up old tokens and look for a valid one
    existing_valid_token = get_and_clean_existing_tokens(username, password, tokens_url, delete_token_url)
    
    if existing_valid_token:
        return existing_valid_token

    # Step 2: If no healthy tokens exist, generate a new one
    post_response = requests.post(token_url, headers=HEADERS, auth=HTTPBasicAuth(username, password))
    token_data = post_response.json()
    
    if "error" in token_data: 
        error_msg = token_data.get('error_description', token_data['error'])
        print(f"Error encountered when trying to retrieve bearer token: {error_msg}", file=sys.stderr)
        return None
            
    return token_data["access_token"]

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Manage and retrieve an Earthdata Login (EDL) Bearer Token.")
    parser.add_argument(
        "env", 
        type=str, 
        choices=["uat", "ops"], 
        help="The target environment: 'uat' or 'ops'."
    )
    
    args = parser.parse_args()
    
    token = generate_edl_token(args.env)
    
    if token:
        # Prints directly to stdout so it can be piped or captured
        print(token)
    else:
        sys.exit(1)
