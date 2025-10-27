#!/usr/bin/env python3

import os
import sys
import logging

# Configure logging to stderr so it appears in GitHub Actions logs
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s: %(message)s',
    stream=sys.stderr
)

# Get token from environment
token = os.environ.get("CMR_BEARER_TOKEN")

# Log the token safely
if token:
    logging.info(f"Token is set. First 8 chars: {token[:8]}...")
else:
    logging.warning("CMR_BEARER_TOKEN is not set")