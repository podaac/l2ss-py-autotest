import json
import logging
import os
import pathlib
import shutil
from typing import List, Dict

import cmr
import harmony
import numpy as np
import pytest
import requests
import xarray
from requests.auth import HTTPBasicAuth


# @pytest.fixture(scope="session")
# def collection_concept_id(pytestconfig):
#     return pytestconfig.getoption("concept_id")


@pytest.fixture(scope="session")
def env(pytestconfig):
    return pytestconfig.getoption("env")


@pytest.fixture(scope="session")
def cmr_mode(env):
    if env == 'uat':
        return cmr.CMR_UAT
    else:
        return cmr.CMR_OPS


@pytest.fixture(scope="session")
def harmony_env(env):
    if env == 'uat':
        return harmony.config.Environment.UAT
    else:
        return harmony.config.Environment.OPS


@pytest.fixture(scope="session")
def request_session():
    with requests.Session() as s:
        s.headers.update({'User-agent': 'l2ss-py-autotest'})
        yield s


@pytest.fixture(scope="session")
def bearer_token(env: str, request_session: requests.Session) -> str:
    tokens = []
    headers: dict = {'Accept': 'application/json'}
    url: str = f"https://{'uat.' if env == 'uat' else ''}urs.earthdata.nasa.gov/api/users"

    # First just try to get a token that already exists
    try:
        resp = request_session.get(url + "/tokens", headers=headers,
                                   auth=HTTPBasicAuth(os.environ['CMR_USER'], os.environ['CMR_PASS']))
        response_content = json.loads(resp.content)

        for x in response_content:
            tokens.append(x['access_token'])

    except:  # noqa E722
        logging.warning("Error getting the token - check user name and password", exc_info=True)

    # No tokens exist, try to create one
    if not tokens:
        try:
            resp = request_session.post(url + "/token", headers=headers,
                                        auth=HTTPBasicAuth(os.environ['CMR_USER'], os.environ['CMR_PASS']))
            response_content: dict = json.loads(resp.content)
            tokens.append(response_content['access_token'])
        except:  # noqa E722
            logging.warning("Error getting the token - check user name and password", exc_info=True)

    # If still no token, then we can't do anything
    if not tokens:
        pytest.skip("Unable to get bearer token from EDL")

    return next(iter(tokens))


@pytest.fixture(scope="function")
def granule_json(collection_concept_id: str, cmr_mode: str, bearer_token: str) -> dict:
    '''
    This fixture defines the strategy used for picking a granule from a collection for testing

    Parameters
    ----------
    collection_concept_id
    cmr_mode
    bearer_token

    Returns
    -------
    umm_json for selected granule
    '''
    cmr_url = f"{cmr_mode}granules.umm_json?collection_concept_id={collection_concept_id}&sort_key=-start_date&token={bearer_token}&page_size=1"

    with requests.Session() as s:
        response_json = s.get(cmr_url).json()

    if 'items' in response_json and len(response_json['items']) > 0:
        return response_json['items'][0]
    elif cmr_mode == cmr.CMR_UAT:
        pytest.skip(f"No granules found for UAT collection {collection_concept_id}")


@pytest.fixture(scope="function")
def original_granule_localpath(granule_json: dict, tmp_path) -> pathlib.Path:
    urls = granule_json['umm']['RelatedUrls']
    print(urls)

    def download_file(url):
        local_filename = tmp_path.joinpath(f"{granule_json['meta']['concept-id']}_original_granule.nc")
        with requests.get(url, stream=True) as r:
            with open(local_filename, 'wb') as f:
                shutil.copyfileobj(r.raw, f)
        return local_filename

    granule_url = None
    for x in urls:
        if x.get('Type') == "GET DATA" and x.get('Subtype') in [None, 'DIRECT DOWNLOAD'] and '.bin' not in x.get('URL'):
            granule_url = x.get('URL')

    if granule_url:
        return download_file(granule_url)
    else:
        pytest.skip(f"Unable to find download URL for {granule_json['meta']['concept-id']}")


@pytest.fixture(scope="function")
def collection_variables(cmr_mode, collection_concept_id, env, bearer_token):
    collection_query = cmr.queries.CollectionQuery(mode=cmr_mode)
    variable_query = cmr.queries.VariableQuery(mode=cmr_mode)

    collection_res = collection_query.concept_id(collection_concept_id).token(bearer_token).get()[0]
    collection_associations = collection_res.get("associations")
    variable_concept_ids = collection_associations.get("variables")

    if variable_concept_ids is None and env == 'uat':
        pytest.skip('There are no umm-v associated with this collection in UAT')

    variables = []
    for i in range(0, len(variable_concept_ids), 40):
        variables_items = variable_query \
            .concept_id(variable_concept_ids[i:i + 40]) \
            .token(bearer_token) \
            .format('umm_json') \
            .get_all()
        variables.extend(json.loads(variables_items[0]).get('items'))

    return variables


def get_bounding_box(granule_umm_json):
    # Find Bounding box for granule
    try:
        bounding_box = granule_umm_json['umm']['SpatialExtent']['HorizontalSpatialDomain']['Geometry'][
            'BoundingRectangles'][0]

        north = bounding_box.get('NorthBoundingCoordinate')
        south = bounding_box.get('SouthBoundingCoordinate')
        west = bounding_box.get('WestBoundingCoordinate')
        east = bounding_box.get('EastBoundingCoordinate')

    except KeyError:
        longitude_list = []
        latitude_list = []
        polygons = granule_umm_json['umm']['SpatialExtent']['HorizontalSpatialDomain']['Geometry'].get(
            'GPolygons')
        lines = granule_umm_json['umm']['SpatialExtent']['HorizontalSpatialDomain']['Geometry'].get('Lines')
        if polygons:
            for polygon in polygons:
                points = polygon['Boundary']['Points']
                for point in points:
                    longitude_list.append(point.get('Longitude'))
                    latitude_list.append(point.get('Latitude'))
                break
        elif lines:
            points = lines[0].get('Points')
            for point in points:
                longitude_list.append(point.get('Longitude'))
                latitude_list.append(point.get('Latitude'))
        north = max(latitude_list)
        south = min(latitude_list)
        west = min(longitude_list)
        east = max(longitude_list)

    return north, south, east, west


def get_coordinate_vars_from_umm(collection_variable_list: List[Dict]):
    lon_var, lat_var, time_var = None, None, None
    for var in collection_variable_list:
        if 'VariableSubType' in var['umm']:
            var_subtype = var.get('umm').get('VariableSubType')
            if var_subtype == "LONGITUDE":
                lon_var = var
            if var_subtype == "LATITUDE":
                lat_var = var
            if var_subtype == "TIME":
                time_var = var

    return lon_var, lat_var, time_var


def get_science_vars(collection_variable_list: List[Dict]):
    science_vars = []
    for var in collection_variable_list:
        if 'VariableType' in var['umm'] and 'SCIENCE_VARIABLE' == var['umm']['VariableType']:
            science_vars.append(var)
    return science_vars


def get_variable_name_from_umm_json(variable_umm_json):
    name = variable_umm_json['umm']['Name']

    return "/".join(name.strip("/").split('/')[1:]) if '/' in name else name


def get_lat_lon_var_names(dataset):
    try:
        return dataset.cf.coordinates['latitude'][0], dataset.cf.coordinates['longitude'][0]
    except:
        return None, None


def test_spatial_subset(collection_concept_id, env, granule_json, original_granule_localpath: pathlib.Path,
                        collection_variables,
                        harmony_env, tmp_path: pathlib.Path):
    test_spatial_subset.__doc__ = f"Verify spatial subset for {collection_concept_id} in {env}"

    logging.info("Using granule %s for test", granule_json['meta']['concept-id'])
    logging.info(json.dumps(granule_json))

    # Compute a box that is smaller than the granule extent bounding box
    north, south, east, west = get_bounding_box(granule_json)
    north = north - abs(.05 * (north - south))
    south = south + abs(.05 * (north - south))
    west = west + abs(.05 * (east - west))
    east = east - abs(.05 * (east - west))

    # Build harmony request
    harmony_client = harmony.Client(env=harmony_env)
    request_bbox = harmony.BBox(w=west, s=south, e=east, n=north)
    request_collection = harmony.Collection(id=collection_concept_id)
    harmony_request = harmony.Request(collection=request_collection, spatial=request_bbox,
                                      granule_id=[granule_json['meta']['concept-id']])
    logging.info("Sending harmony request %s", harmony_client.request_as_curl(harmony_request))

    # Submit harmony request and download result
    job_id = harmony_client.submit(harmony_request)
    harmony_client.wait_for_processing(job_id, show_progress=True)
    subsetted_filepath = None
    for filename in [file_future.result()
                     for file_future
                     in harmony_client.download_all(job_id, directory=f'{tmp_path}', overwrite=True)]:
        logging.info(f'Downloaded: %s', filename)
        subsetted_filepath = pathlib.Path(filename)

    # Verify spatial subset worked
    import cf_xarray
    original_ds = xarray.open_dataset(original_granule_localpath)
    subsetted_ds = xarray.open_dataset(subsetted_filepath)
    print(original_ds.cf)
    print(subsetted_ds.cf)

    # if "latitude" in subsetted_ds.cf.coordinates and "latitude" in original_ds.cf.coordinates:
    #     assert original_ds.cf.min('latitude') < subsetted_ds.cf.min('latitude')
    #     assert original_ds.cf.max('latitude') > subsetted_ds.cf.max('latitude')
    # if "longitude" in subsetted_ds.cf.coordinates and "longitude" in original_ds.cf.coordinates:
    #     assert original_ds.cf.min('longitude') < subsetted_ds.cf.min('longitude')
    #     assert original_ds.cf.max('longitude') > subsetted_ds.cf.max('longitude')

    lat_var_name, lon_var_name = get_lat_lon_var_names(subsetted_ds)
    assert lat_var_name and lon_var_name

    if science_vars := get_science_vars(collection_variables):
        science_var_name = science_vars[0]['umm']['Name']
    else:
        # Can't find a science var in UMM-V, just pick one
        science_var_name = next(iter([v for v in subsetted_ds.data_vars if
                                      str(v) not in subsetted_ds.cf[['latitude']] and str(v) not in subsetted_ds.cf[
                                          ['longitude']]]))

    var_ds = subsetted_ds[science_var_name]

    # if group:
    #     lat_var = lat_var.split('/')[-1]
    #     lon_var = lon_var.split('/')[-1]

    try:
        msk = np.logical_not(np.isnan(var_ds.data.squeeze()))
        llat = subsetted_ds[lat_var_name].where(msk)
        llon = subsetted_ds[lon_var_name].where(msk)
    except ValueError:
        llat = subsetted_ds[lat_var_name]
        llon = subsetted_ds[lon_var_name]

    lat_max = llat.max()
    lat_min = llat.min()

    lon_min = llon.min()
    lon_max = llon.max()

    lon_min = (lon_min + 180) % 360 - 180
    lon_max = (lon_max + 180) % 360 - 180

    lat_var_fill_value = subsetted_ds[lat_var_name].encoding.get('_FillValue')
    lon_var_fill_value = subsetted_ds[lon_var_name].encoding.get('_FillValue')

    if lat_var_fill_value:
        if (lat_max <= north or np.isclose(lat_max, north)) and (lat_min >= south or np.isclose(lat_min, south)):
            print("Successful Latitude subsetting")
        elif np.isnan(lat_max) and np.isnan(lat_min):
            print("Partial Lat Success - no Data")
        else:
            assert False

    if lon_var_fill_value:
        if (lon_max <= east or np.isclose(lon_max, east)) and (lon_min >= west or np.isclose(lon_min, west)):
            print("Successful Longitude subsetting")
        elif np.isnan(lon_max) and np.isnan(lon_min):
            print("Partial Lon Success - no Data")
        else:
            assert False

    assert original_granule_localpath.stat().st_size > subsetted_filepath.stat().st_size
