# l2ss-py-autotest

This repository contains functional/integration tests for l2ss-py. It also includes github
action workflows for automatically running these tests whenever a new collection gets
associated to the l2ss-py UMM-S record.

## How it works

1. Every 5 minutes the `cmr_association_diff.py` script is run against UAT and OPS. This script looks at the collection concept ids in `tests/cmr/l2ss-py/*_associations.txt` and compares them to the associations in CMR (see [diff.yml](.github/workflows/diff.yml))
2. For every collection concept id that exists in CMR association but does NOT exist in the .txt file in this repository, a new PR is opened in this repository with the new collection concept id as the title and branch name.
3. When a pull request is created or updated in this repository and the base branch name starts with `diff/uat` or `diff/ops`, the tests will be executed for that collection (see [verify.yml](.github/workflows/verify.yml))
4. The results of the test will be recorded as a status check for the PR
   1. If all tests pass: The pr will be labeled `verified` and automatically merged
   2. If any test fails or has an unknown error: The pr will be labeled `bug` and `failed verification` and will remain open
   3. If any tests are skipped: The pr will be labeled `unverified` and will remain open 

## What to do if tests fail

If a test fails, meaning an assertion did not succeed, or an unknown error occurs action must be taken. The cause of the failure should be determined and fixed.
A failing test generally indicates an issue with either metadata or l2ss-py itself and may require additional steps.
In some cases, the test may need to be updated to account for a unique edge case.

## What to do if tests are skipped

Generally a skipped test indicates that verification was unable to complete.
There are a few situations where tests get skipped (for example: in UAT if there are no UMM-Var records associated to the collection)
When this happens, one of two things can be done:
  - Comment on the PR explaining why it is ok to not verify that collection and ask a repository admin to manually merge the PR
  - Fix the reason that caused the test to be skipped. For example, if it was skipped because there are no UMM-Var entries in UAT, then add UMM-Var entries to UAT and re-run the failed check

