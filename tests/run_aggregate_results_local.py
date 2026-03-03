import argparse
import os

from aggregate_results import main as aggregate_main


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run aggregate_results.main() against an existing job-status "
            "output directory without re-running tests."
        )
    )
    parser.add_argument(
        "--job-status-root",
        required=True,
        help=(
            "Path to the directory that contains per-job subdirectories "
            "with job_status.json files (the parent of the job-status/* folders)."
        ),
    )
    parser.add_argument(
        "--env",
        dest="regression_env",
        help="Optional override for REGRESSION_ENV (e.g. uat or ops).",
    )
    parser.add_argument(
        "--github-repo",
        dest="github_repository",
        help="Optional override for GITHUB_REPOSITORY (e.g. owner/repo).",
    )
    parser.add_argument(
        "--github-token",
        dest="github_token",
        help="Optional override for GITHUB_TOKEN.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    # Point aggregate_results at the provided job-status root.
    os.environ["JOB_STATUS_ROOT"] = args.job_status_root

    # Optionally override environment used by aggregate_results.
    if args.regression_env:
        os.environ["REGRESSION_ENV"] = args.regression_env
    if args.github_repository:
        os.environ["GITHUB_REPOSITORY"] = args.github_repository
    if args.github_token:
        os.environ["GITHUB_TOKEN"] = args.github_token

    aggregate_main()


if __name__ == "__main__":
    main()

