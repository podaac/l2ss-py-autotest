#!/usr/bin/env python3
"""
Remove CMR ID association files for items in the input list.

Usage:
  python remove_association_files.py --list path/to/list.txt --env {uat,ops}

The list file should contain one item per line, where the first token on the
line is the file identifier to remove. For example lines like:
  C3385050059-OB_CLOUD ()
  C3385050045-OB_CLOUD ()

This script will delete matching files from tests/cmr/l2ss-py/{env}/<fileid>.
"""

import argparse
from pathlib import Path
import sys


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Remove corresponding files in tests/cmr/l2ss-py/{env}/ based on a list "
            "of items (first token per line is treated as the file id)."
        )
    )
    parser.add_argument(
        "--list",
        required=True,
        dest="list_path",
        help="Path to input list file containing items; first token is the file id.",
    )
    parser.add_argument(
        "--env",
        required=True,
        choices=["uat", "ops"],
        help="Environment directory under tests/cmr/l2ss-py to clean (uat or ops).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only print what would be deleted without removing files.",
    )
    return parser.parse_args()


def iter_file_ids(list_file: Path):
    with list_file.open("r", encoding="utf-8") as fh:
        for raw_line in fh:
            line = raw_line.strip()
            if not line:
                continue
            # Extract the first token (before any whitespace or opening parenthesis)
            token = line.split()[0]
            # In case lines are like "ID (something)", ensure we strip trailing '(' if attached
            file_id = token.split("(")[0].strip()
            if file_id:
                yield file_id


def main() -> int:
    args = parse_args()

    list_file = Path(args.list_path).expanduser().resolve()
    if not list_file.exists():
        print(f"List file not found: {list_file}", file=sys.stderr)
        return 1

    # Base directory: repo_root/tests/cmr/l2ss-py/{env}
    repo_root = Path(__file__).resolve().parent
    base_dir = repo_root / "tests" / "cmr" / "l2ss-py" / args.env
    if not base_dir.exists():
        print(f"Environment directory not found: {base_dir}", file=sys.stderr)
        return 1

    exit_code = 0
    for file_id in iter_file_ids(list_file):
        target_path = base_dir / file_id
        if target_path.exists():
            if args.dry_run:
                print(f"DRY-RUN would remove: {target_path}")
            else:
                try:
                    target_path.unlink()
                    print(f"Removed: {target_path}")
                except OSError as exc:
                    print(f"Failed to remove {target_path}: {exc}", file=sys.stderr)
                    exit_code = 1
        else:
            print(f"Not found (skip): {target_path}")

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())


