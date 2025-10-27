#!/usr/bin/env python3
"""
Script to retrieve a bearer token for NASA's CMR API.

Usage:
    python get_cmr_token.py <env>
    
Arguments:
    env: Environment to use ('uat' or 'ops')
    
Environment Variables:
    CMR_BEARER_TOKEN: Optional cached token (checked first)
    CMR_USER: Required username for EDL authentication
    CMR_PASS: Required password for EDL authentication
    
Examples:
    python get_cmr_token.py ops
    python get_cmr_token.py uat
    
Exit Codes:
    0: Success (token printed to stdout)
    1: Error (details in stderr)
"""

import os
import sys
import logging
import requests
from requests.auth import HTTPBasicAuth

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s: %(message)s',
    stream=sys.stderr
)


def get_bearer_token(env: str) -> str:
    """
    Retrieve bearer token for CMR API from cache or EDL.
    
    Args:
        env: Environment ('uat' or 'ops')
        
    Returns:
        Bearer token string
        
    Raises:
        ValueError: If required environment variables are missing
        RuntimeError: If token retrieval fails
    """
    # Validate required credentials are present
    username = os.environ.get('CMR_USER')
    password = os.environ.get('CMR_PASS')
    
    if not username or not password:
        raise ValueError("CMR_USER and CMR_PASS environment variables must be set")
    
    # Build URL based on environment
    url = f"https://{'uat.' if env == 'uat' else ''}urs.earthdata.nasa.gov/api/users/find_or_create_token"
    logging.info(f"Requesting token from {url}")
    
    try:
        with requests.Session() as session:
            resp = session.post(
                url,
                auth=HTTPBasicAuth(username, password),
                timeout=30
            )
            resp.raise_for_status()
            
            response_content = resp.json()
            token = response_content.get('access_token')
            
            if not token:
                raise RuntimeError(f"No access_token in response from {url}")
            
            logging.info("Successfully retrieved token")
            return token
            
    except requests.exceptions.HTTPError as e:
        raise RuntimeError(f"HTTP error getting token (status {resp.status_code}): {e}")
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"Request error getting token: {e}")
    except (ValueError, KeyError) as e:
        raise RuntimeError(f"Invalid response format from EDL: {e}")


def main():
    """Main entry point for the script."""
    # Check command line arguments
    if len(sys.argv) != 2:
        print("Usage: python get_cmr_token.py <env>", file=sys.stderr)
        print("  env: 'uat' or 'ops'", file=sys.stderr)
        sys.exit(1)
    
    env = sys.argv[1].lower()
    
    # Validate environment argument
    if env not in ('uat', 'ops'):
        print(f"Error: Invalid environment '{env}'. Must be 'uat' or 'ops'", file=sys.stderr)
        sys.exit(1)
    
    try:
        token = get_bearer_token(env)
        # Print token to stdout (can be captured in GitHub Actions)
        print(token)
        sys.exit(0)
        
    except ValueError as e:
        logging.error(f"Configuration error: {e}")
        sys.exit(1)
    except RuntimeError as e:
        logging.error(f"Token retrieval failed: {e}")
        sys.exit(1)
    except Exception as e:
        logging.error(f"Unexpected error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()