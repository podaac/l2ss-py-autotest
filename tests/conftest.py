import os
import pathlib
import json
import pytest
import re
import create_or_update_issue
from groq import Groq
import time
import re

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

        associations  = [
            "C1275819072-LAADSCDUAT",
            "C1229246430-GES_DISC",
            "C1233405381-GES_DISC",
            "C1261072651-POCLOUD",
            "C1261072650-POCLOUD",
            "C1268674275-GES_DISC",
            "C1240739526-POCLOUD",
            "C1256946216-ASDC_DEV2",
            "C1215667655-GES_DISC"
        ]

        if 'collection_concept_id' in metafunc.fixturenames and associations is not None:
            metafunc.parametrize("collection_concept_id", associations)
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

    pattern = r"bearer_token = '.*?'"
    cleaned_text = re.sub(pattern, "", error_message)
    
    return cleaned_text


def pytest_terminal_summary(terminalreporter, exitstatus, config):

    failed = []
    failed_tests = terminalreporter.stats.get('failed', [])
    error_tests = terminalreporter.stats.get('error', [])

    all_failed_test = failed_tests + error_tests

    if all_failed_test:
        for report in all_failed_test:

            concept_id = list(report.keywords)[3]

            # Extract the test name and exception message from the report
            test_name = report.nodeid
            test_type = None

            if "spatial" in test_name:
                test_type = "spatial"
            elif "temporal" in test_name:
                test_type = "temporal"

            try:
                full_message = get_error_message(report)
            except Exception:
                full_message = "Unable to retrive error message"

            print(type(full_message))
            print(full_message)

            failed.append({
                "concept_id": concept_id,
                "test_type": test_type,
                "message": full_message
            })

    test_results = {
        'failed': failed, 
    }

    env = config.option.env

    if config.option.regression or True:

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

