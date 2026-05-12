#!/usr/bin/env python3
"""Prepend a runtime alert to the fixed regression issue for an environment."""

from __future__ import annotations

import argparse
import os
import re
import sys
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from typing import Iterable

import requests


ISSUE_NUMBERS = {
    "UAT": 3919,
    "OPS": 3973,
}

ALERT_BLOCK_RE = re.compile(
    r"<!-- regression-alert:start -->.*?<!-- regression-alert:end -->\n*",
    re.DOTALL,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Prepend an alert message to the fixed regression issue body for "
            "the selected environment."
        )
    )
    parser.add_argument(
        "--env",
        required=True,
        help="Target environment: uat or ops.",
    )
    parser.add_argument(
        "--alert",
        action="append",
        dest="alerts",
        default=[],
        help="Alert text to prepend. Pass multiple times to include more than one line.",
    )
    return parser.parse_args()


def get_issue_number(env: str) -> int:
    env_key = env.upper()
    if env_key not in ISSUE_NUMBERS:
        raise ValueError(f"Unsupported environment: {env}")
    return ISSUE_NUMBERS[env_key]


def build_alert_block(alerts: Iterable[str]) -> str:
    pacific = ZoneInfo("America/Los_Angeles")
    timestamp = datetime.now(timezone.utc).astimezone(pacific).strftime("%Y-%m-%d %H:%M:%S %Z")
    lines = [
        "<!-- regression-alert:start -->",
        f"**Alert** - {timestamp}",
    ]
    for alert in alerts:
        lines.append(f"- {alert}")
    lines.append("<!-- regression-alert:end -->")
    return "\n".join(lines)


def strip_existing_alert(body: str) -> str:
    return ALERT_BLOCK_RE.sub("", body or "")


def fetch_issue(repo: str, token: str, issue_number: int) -> dict:
    url = f"https://api.github.com/repos/{repo}/issues/{issue_number}"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github+json",
    }
    response = requests.get(url, headers=headers, timeout=20)
    response.raise_for_status()
    return response.json()


def update_issue(repo: str, token: str, issue_number: int, body: str) -> None:
    url = f"https://api.github.com/repos/{repo}/issues/{issue_number}"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github+json",
    }
    response = requests.patch(url, headers=headers, json={"body": body}, timeout=20)
    response.raise_for_status()


def main() -> int:
    args = parse_args()

    repo = os.environ.get("GITHUB_REPOSITORY")
    token = os.environ.get("GITHUB_TOKEN")
    if not repo or not token:
        print("GITHUB_REPOSITORY and GITHUB_TOKEN are required.", file=sys.stderr)
        return 1

    if not args.alerts:
        print("At least one --alert message is required.", file=sys.stderr)
        return 1

    try:
        issue_number = get_issue_number(args.env)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    issue = fetch_issue(repo, token, issue_number)
    existing_body = strip_existing_alert(issue.get("body", ""))
    existing_body = existing_body.lstrip("\n")

    alert_block = build_alert_block(args.alerts)
    if existing_body:
        new_body = f"{alert_block}\n\n{existing_body}"
    else:
        new_body = alert_block

    update_issue(repo, token, issue_number, new_body)
    print(f"Updated issue #{issue_number} with alert for {args.env.upper()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
