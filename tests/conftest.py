import os
import pathlib

import pytest

try:
    os.environ['CMR_USER']
except KeyError:
    raise KeyError(f'CMR_USER environment variable is required')

try:
    os.environ['CMR_PASS']
except KeyError:
    raise KeyError(f'CMR_PASS environment variable is required')


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
        associations = [os.listdir(cmr_dirpath.joinpath(association_dir))]

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
