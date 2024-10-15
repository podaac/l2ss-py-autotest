import os
import pathlib
import json
import pytest
import re
import create_or_update_issue

try:
    os.environ['CMR_USER']
except KeyError:
    raise KeyError(f'CMR_USER environment variable is required')

try:
    os.environ['CMR_PASS']
except KeyError:
    raise KeyError(f'CMR_PASS environment variable is required')

# Custom plugin to record results
class ResultsRecorder:
    def __init__(self):
        self.results = []

    def record(self, result):
        self.results.append(result)

    def get_results(self):
        return self.results

    def pytest_sessionfinish(self, session):
        # At the end of the test session, you can save or process the results
        print("\nRecording test results:")
        for result in self.results:
            print(result)

# Fixture to provide an instance of the custom plugin
@pytest.fixture
def record_results(request):
    recorder = ResultsRecorder()
    request.config.pluginmanager.register(recorder)
    yield recorder.record
    request.config.pluginmanager.unregister(recorder)


def pytest_addoption(parser):
    parser.addoption("--env", action="store", choices=['uat', 'ops'], help="Environment to use for testing",
                     required=True)

    group = parser.getgroup('test_mode')
    group.addoption("--concept_id", action="store", help="Concept ID of single collection to test")
    group.addoption("--regression", action="store_true", help="Run tests for all known collection associations")


def pytest_generate_tests(metafunc):
    if metafunc.config.option.regression:
        cmr_dirpath = pathlib.Path('cmr/l2ss-py')

        association_dir = 'uat' if metafunc.config.option.env == 'uat' else 'ops'
        associations = os.listdir(cmr_dirpath.joinpath(association_dir))
        midpoint = len(associations) // 6

        if 'collection_concept_id' in metafunc.fixturenames and associations is not None:
            metafunc.parametrize("collection_concept_id", associations[:midpoint])
    else:
        collection_concept_id = metafunc.config.option.concept_id
        if 'collection_concept_id' in metafunc.fixturenames and collection_concept_id is not None:
            metafunc.parametrize("collection_concept_id", [collection_concept_id])


@pytest.fixture(scope="session", autouse=True)
def log_global_env_facts(record_testsuite_property, request):
    record_testsuite_property("concept_id", request.config.getoption('concept_id'))
    record_testsuite_property("env", request.config.getoption('env'))


def get_error_message(report):

    # If it's a regular test failure (not a skipped or xfailed test)
    if hasattr(report, 'longreprtext'):
        # Extract the short-form failure reason (in pytest >= 6)
        error_message = report.longreprtext
    else:
        # Fallback if longreprtext is not available
        if isinstance(report.longrepr, tuple):
            error_message = report.longrepr[2]
        else:
            error_message = str(report.longrepr)

    exception_pattern = r"E\s+(\w+):\s+\(([^,]+),\s+'(.+?)'\)"
    match = re.search(exception_pattern, error_message)

    if match:
        exception_type = match.group(1)  # 'Exception'
        exception_reason = match.group(2)  # 'Not Found'
        exception_message = match.group(3)  # 'Error: EULA ... could not be found.'

        # Combine all into one message
        full_message = f"Exception Type: {exception_type}, Reason: {exception_reason}, Message: {exception_message}"
        return full_message
    else:
        return "No exception found."


def pytest_terminal_summary(terminalreporter, exitstatus, config):

    filtered_success, success, skipped, failed = [], [], [], []

    failed_tests = terminalreporter.stats.get('failed', [])
    skipped_tests = terminalreporter.stats.get('skipped', [])
    success_tests = terminalreporter.stats.get('passed', [])

    print("======================================================")
    print(failed_tests)
    print(len(failed_tests))
    print("======================================================")

    if failed_tests:
        for report in failed_tests:

            concept_id = list(report.keywords)[3]

            # Extract the test name and exception message from the report
            test_name = report.nodeid
            test_type = None

            if "spatial" in test_name:
                test_type = "spatial"
            elif "temporal" in test_name:
                test_type = "temporal"

            full_message = get_error_message(report)

            failed.append({
                "concept_id": concept_id,
                "test_type": test_type,
                "message": full_message
            })

    if skipped_tests:
        for report in skipped_tests:

            concept_id = list(report.keywords)[3]

            # Extract the test name and exception message from the report
            test_name = report.nodeid
            test_type = None

            if "spatial" in test_name:
                test_type = "spatial"
            elif "temporal" in test_name:
                test_type = "temporal"

            # If it's a regular test failure (not a skipped or xfailed test)
            if hasattr(report, 'longreprtext'):
                # Extract the short-form failure reason (in pytest >= 6)
                error_message = report.longreprtext
            else:
                # Fallback if longreprtext is not available
                if isinstance(report.longrepr, tuple):
                    error_message = report.longrepr[2]
                else:
                    error_message = str(report.longrepr)

            error = "UNKNOWN"
            if isinstance(report.longreprtext, str):
                tuple_error = eval(report.longreprtext)
                error = tuple_error[2]

            skipped.append({
                "concept_id": concept_id,
                "test_type": test_type,
                "message": error
            })

    print("======================================================")
    print(failed)
    print("======================================================")

    test_results = {
        'success': filtered_success,
        'failed': failed, 
        'skipped': skipped
    }

    repo_name = os.getenv("GITHUB_REPOSITORY")
    github_token = os.getenv("GITHUB_TOKEN")
    env = os.getenv("ENV")
    create_or_update_issue.create_or_update_issue(repo_name, github_token, env, test_results)

    print("======================================================")
    print(test_results)
    print("======================================================")

    env = config.option.env

    if config.option.regression:

        file_path = f'{env}_regression_results.json'
        with open(file_path, 'w') as file:
            json.dump(test_results, file)

        for outcome, tests in test_results.items():
            if tests:
                print(f'{outcome.capitalize()} Tests')
                print(tests)
                file_path = f'{env}_{outcome}.json'
                with open(file_path, 'w') as file:
                    json.dump(tests, file)


