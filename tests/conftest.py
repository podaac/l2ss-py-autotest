import os
import pathlib
import json
import pytest

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
        cmr_dirpath = pathlib.Path('cmr')

        association_dir = 'uat' if metafunc.config.option.env == 'uat' else 'ops'
        associations = os.listdir(cmr_dirpath.joinpath(association_dir))

        if 'collection_concept_id' in metafunc.fixturenames and associations is not None:
            metafunc.parametrize("collection_concept_id", associations[0:1])
    else:
        collection_concept_id = metafunc.config.option.concept_id
        if 'collection_concept_id' in metafunc.fixturenames and collection_concept_id is not None:
            metafunc.parametrize("collection_concept_id", [collection_concept_id])


@pytest.fixture(scope="session", autouse=True)
def log_global_env_facts(record_testsuite_property, request):
    record_testsuite_property("concept_id", request.config.getoption('concept_id'))
    record_testsuite_property("env", request.config.getoption('env'))


def pytest_terminal_summary(terminalreporter, exitstatus, config):

    success, skipped, failed = [], [], []
    test_results = {'success': success, 'failed': failed, 'skipped': skipped}

    # the fourth keyword is the collection concept id may change if we change the test inputs
    skipped.extend([list(skip.keywords)[3] for skip in terminalreporter.stats.get('skipped', [])])
    failed.extend([list(failed.keywords)[3] for failed in terminalreporter.stats.get('failed', [])])
    success.extend([list(passed.keywords)[3] for passed in terminalreporter.stats.get('passed', [])])

    env = config.option.env

    if config.option.regression:
        for outcome, tests in test_results.items():
            if tests:
                print(f'{outcome.capitalize()} Tests')
                print(tests)
                file_path = f'{env}_{outcome}.json'
                with open(file_path, 'w') as file:
                    json.dump(tests, file)
