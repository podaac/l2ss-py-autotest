import json
import logging
import os
import pathlib
import shutil
from typing import List, Dict
from datetime import datetime, timedelta

import cf_xarray as cfxr
import harmony
import netCDF4
import numpy as np
import podaac.subsetter.subset
import pytest
import requests
import xarray
import csv

import cmr
import token_utils

VALID_LATITUDE_VARIABLE_NAMES = ['lat', 'latitude']
VALID_LONGITUDE_VARIABLE_NAMES = ['lon', 'longitude']

assert cfxr, "cf_xarray adds extensions to xarray on import"
GROUP_DELIM = '__'
DEFAULT_SPATIAL_BBOX_SCALE = 0.95
DEFAULT_TEMPORAL_FRACTION = 0.5
CUSTOM_TESTS_DIRNAME = "custom"


def fetch_bearer_token_by_provider(env: str, request_session: requests.Session, token_provider: str) -> str:
    try:
        token = token_utils.fetch_bearer_token_by_provider(
            env, token_provider, request_session=request_session
        )
        if token:
            return token
    except Exception as e:
        logging.warning(f"Error getting token from EDL: {e}", exc_info=True)
    pytest.fail("Unable to get bearer token from EDL or environment variable")


def is_auth_error(exception: Exception) -> bool:
    msg = str(exception).lower()
    return any(keyword in msg for keyword in ["401", "403", "unauthorized", "forbidden", "token", "expired"])

@pytest.fixture(scope="session")
def env(pytestconfig):
    return pytestconfig.getoption("env")


@pytest.fixture(scope="session")
def token_provider(pytestconfig):
    return pytestconfig.getoption("token_provider")


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
        return harmony.config.Environment.PROD


@pytest.fixture(scope="session")
def request_session():
    with requests.Session() as s:
        s.headers.update({'User-agent': 'l2ss-py-autotest'})
        yield s


# Helper function to read a single CSV file and return a set of skip entries
def read_skip_list(csv_file):
    with open(csv_file, newline='') as f:
        reader = csv.reader(f)
        return {row[0].strip() for row in reader}

def normalize_provider_name(name: str) -> str:
    if not name:
        return ""
    return name.strip().upper().replace("-", "_").replace(" ", "_")


def parse_provider_from_concept_id(collection_concept_id: str) -> str:
    if not collection_concept_id or "-" not in collection_concept_id:
        return ""
    return normalize_provider_name(collection_concept_id.split("-")[-1])


def read_overrides_file(path: str) -> dict:
    if not path or not os.path.exists(path):
        return {}
    with open(path) as f:
        return json.load(f)


def resolve_overrides(overrides: dict, collection_concept_id: str) -> dict:
    if not overrides:
        return {}

    provider = parse_provider_from_concept_id(collection_concept_id)

    provider_overrides = {}
    providers = overrides.get("providers", {})
    if provider:
        provider_overrides = providers.get(provider, {}) or providers.get(provider.lower(), {}) or providers.get(provider.upper(), {}) or {}

    collection_overrides = {}
    collections = overrides.get("collections", {})
    if collection_concept_id in collections:
        collection_overrides = collections[collection_concept_id] or {}
    else:
        # Case-insensitive key matching for convenience
        for key, value in collections.items():
            if key.lower() == collection_concept_id.lower():
                collection_overrides = value or {}
                break

    group_overrides = {}
    groups = overrides.get("collection_groups", {}) or {}
    for _, group in groups.items():
        members = group.get("members", []) if isinstance(group, dict) else []
        if collection_concept_id in members:
            group_overrides.update({k: v for k, v in group.items() if k != "members"})

    # Collection overrides win over provider overrides
    return {**provider_overrides, **group_overrides, **collection_overrides}


def _custom_tests_root() -> pathlib.Path:
    return pathlib.Path(__file__).parent.joinpath(CUSTOM_TESTS_DIRNAME)


def _provider_custom_file(provider: str) -> pathlib.Path:
    return _custom_tests_root().joinpath("providers", f"{provider}.py")


def _collection_custom_file(collection_concept_id: str) -> pathlib.Path:
    return _custom_tests_root().joinpath("collections", f"{collection_concept_id}.py")


def _collection_custom_dir(collection_concept_id: str) -> pathlib.Path:
    return _custom_tests_root().joinpath("collections", collection_concept_id)


def _collection_custom_dir_has_tests(collection_concept_id: str) -> bool:
    collection_dir = _collection_custom_dir(collection_concept_id)
    if not collection_dir.exists() or not collection_dir.is_dir():
        return False
    for path in collection_dir.rglob("*.py"):
        if path.name.startswith("test_") or path.name.endswith("_test.py"):
            return True
    return False


def find_custom_tests(collection_concept_id: str) -> dict:
    provider = parse_provider_from_concept_id(collection_concept_id)
    provider_file = _provider_custom_file(provider) if provider else None
    collection_file = _collection_custom_file(collection_concept_id)
    has_provider = bool(provider_file and provider_file.exists())
    has_collection = collection_file.exists() or _collection_custom_dir_has_tests(collection_concept_id)
    return {
        "provider": has_provider,
        "collection": has_collection,
        "any": has_provider or has_collection,
    }


def should_run_generic(test_kind: str, overrides: dict) -> bool:
    """
    Determine whether to run generic tests.
    Supported override keys (bool):
      - run_generic (default True)
      - run_generic_spatial / run_generic_temporal
      - disable_generic (default False)
    """
    if overrides.get("disable_generic") is True:
        return False
    if overrides.get("run_generic") is False:
        return False

    if test_kind == "spatial":
        if overrides.get("run_generic_spatial") is False:
            return False
    if test_kind == "temporal":
        if overrides.get("run_generic_temporal") is False:
            return False
    return True

# Fixture for the first skip list (skip_collections1.csv)
@pytest.fixture(scope="session")
def skip_temporal(env):
    current_dir = os.path.dirname(__file__)
    path = os.path.join(current_dir, f"skip/skip_temporal_{env}.csv")
    return read_skip_list(path)


# Fixture for the second skip list (skip_collections2.csv)
@pytest.fixture(scope="session")
def skip_spatial(env):
    current_dir = os.path.dirname(__file__)
    path = os.path.join(current_dir, f"skip/skip_spatial_{env}.csv")
    return read_skip_list(path)

@pytest.fixture(scope="session")
def overrides_file(pytestconfig):
    configured = pytestconfig.getoption("override_file")
    if configured:
        return configured
    current_dir = os.path.dirname(__file__)
    return os.path.join(current_dir, "overrides.json")


@pytest.fixture(scope="session")
def overrides(overrides_file):
    try:
        return read_overrides_file(overrides_file)
    except Exception as exc:
        pytest.fail(f"Unable to read overrides file at {overrides_file}: {exc}")

@pytest.fixture(scope="session")
def bearer_token_manager(env: str, request_session: requests.Session, token_provider: str):
    token_state = {"token": fetch_bearer_token_by_provider(env, request_session, token_provider)}

    def get_token(refresh: bool = False) -> str:
        if refresh:
            token_state["token"] = fetch_bearer_token_by_provider(env, request_session, token_provider)
        return token_state["token"]

    return get_token


@pytest.fixture(scope="function")
def bearer_token(bearer_token_manager) -> str:
    return bearer_token_manager()


@pytest.fixture(scope="function")
def authed_request(request_session: requests.Session, bearer_token_manager):
    def _request(method: str, url: str, **kwargs):
        headers = dict(kwargs.pop("headers", {}) or {})
        headers['Authorization'] = f'Bearer {bearer_token_manager()}'
        response = request_session.request(method, url, headers=headers, **kwargs)

        if response.status_code in (401, 403):
            logging.info("Token expired or unauthorized response from %s. Refreshing token and retrying once.", url)
            response.close()
            headers['Authorization'] = f'Bearer {bearer_token_manager(refresh=True)}'
            response = request_session.request(method, url, headers=headers, **kwargs)

        return response

    return _request


@pytest.fixture(scope="function")
def granule_json(collection_concept_id: str, cmr_mode: str, authed_request) -> dict:
    '''
    This fixture defines the strategy used for picking a granule from a collection for testing

    Parameters
    ----------
    collection_concept_id
    cmr_mode
    authed_request

    Returns
    -------
    umm_json for selected granule
    '''
    cmr_url = f"{cmr_mode}granules.umm_json?collection_concept_id={collection_concept_id}&sort_key=-start_date&page_size=1"

    response_json = authed_request("GET", cmr_url).json()

    if 'items' in response_json and len(response_json['items']) > 0:
        return response_json['items'][0]
    elif cmr_mode == cmr.CMR_UAT:
        pytest.fail(f"No granules found for UAT collection {collection_concept_id}. CMR search used was {cmr_url}")
    elif cmr_mode == cmr.CMR_OPS:
        pytest.fail(f"No granules found for OPS collection {collection_concept_id}. CMR search used was {cmr_url}")


@pytest.fixture(scope="function")
def original_granule_localpath(granule_json: dict, tmp_path, authed_request) -> pathlib.Path:
    urls = granule_json['umm']['RelatedUrls']

    def download_file(url):
        local_filename = tmp_path.joinpath(f"{granule_json['meta']['concept-id']}_original_granule.nc")
        response = authed_request("GET", url, stream=True)
        with open(local_filename, 'wb') as f:
            shutil.copyfileobj(response.raw, f)
        return local_filename

    granule_url = None
    for x in urls:
        if x.get('Type') == "GET DATA" and x.get('Subtype') in [None, 'DIRECT DOWNLOAD'] and '.bin' not in x.get('URL'):
            granule_url = x.get('URL')

    if granule_url:
        return download_file(granule_url)
    else:
        pytest.fail(f"Unable to find download URL for {granule_json['meta']['concept-id']}")


@pytest.fixture(scope="function")
def collection_variables(cmr_mode, collection_concept_id, env, bearer_token_manager):
    for attempt in range(2):
        token = bearer_token_manager(refresh=(attempt == 1))
        try:
            collection_query = cmr.queries.CollectionQuery(mode=cmr_mode)
            variable_query = cmr.queries.VariableQuery(mode=cmr_mode)

            collection_res = collection_query.concept_id(collection_concept_id).token(token).get()[0]
            collection_associations = collection_res.get("associations")
            variable_concept_ids = collection_associations.get("variables")

            if variable_concept_ids is None:
                pytest.fail(f'There are no umm-v associated with this collection in {env}')

            variables = []
            for i in range(0, len(variable_concept_ids), 40):
                variables_items = variable_query \
                    .concept_id(variable_concept_ids[i:i + 40]) \
                    .token(token) \
                    .format('umm_json') \
                    .get_all()
                variables.extend(json.loads(variables_items[0]).get('items'))

            return variables
        except Exception as e:
            if attempt == 0 and is_auth_error(e):
                logging.info("Auth error while querying collection variables. Refreshing token and retrying once.")
                continue
            raise


def _parse_umm_datetime(value: str) -> datetime:
    try:
        return datetime.strptime(value, '%Y-%m-%dT%H:%M:%S.%fZ')
    except ValueError:
        return datetime.strptime(value, '%Y-%m-%dT%H:%M:%SZ')


def get_middle_temporal_extent(start: str, end: str, fraction: float = DEFAULT_TEMPORAL_FRACTION):
    # Adjust the format to handle cases without fractional seconds
    start_dt = _parse_umm_datetime(start)
    end_dt = _parse_umm_datetime(end)

    if fraction <= 0 or fraction > 1:
        raise ValueError(f"temporal_fraction must be within (0, 1], got {fraction}")

    total_duration = end_dt - start_dt
    if total_duration.total_seconds() <= 0:
        raise ValueError("Invalid temporal range: end time must be after start time")

    keep_duration = total_duration * fraction
    trim = (total_duration - keep_duration) / 2
    new_start_dt = start_dt + trim
    new_end_dt = end_dt - trim

    return {"start": new_start_dt, "end": new_end_dt, "stop": new_end_dt}


def get_bounding_box(granule_umm_json):
    # Find Bounding box for granule
    try:

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

        if not longitude_list or not latitude_list:  # Check if either list is empty
            raise ValueError("Empty longitude or latitude list")

        north = max(latitude_list)
        south = min(latitude_list)
        west = min(longitude_list)
        east = max(longitude_list)

    except (KeyError, ValueError):

        bounding_box = granule_umm_json['umm']['SpatialExtent']['HorizontalSpatialDomain']['Geometry'][
            'BoundingRectangles'][0]

        north = bounding_box.get('NorthBoundingCoordinate')
        south = bounding_box.get('SouthBoundingCoordinate')
        west = bounding_box.get('WestBoundingCoordinate')
        east = bounding_box.get('EastBoundingCoordinate')

    return north, south, east, west


def get_coordinate_vars_from_umm(collection_variable_list: List[Dict]):
    lon_var, lat_var, time_var = {}, {}, {}
    for var in collection_variable_list:
        if 'VariableSubType' in var['umm']:
            var_subtype = var.get('umm').get('VariableSubType')
            if var_subtype == "LONGITUDE":
                lon_var = var
            if var_subtype == "LATITUDE":
                lat_var = var
            if var_subtype == "TIME":
                time_var = var

    return lat_var, lon_var, time_var


def get_science_vars(collection_variable_list: List[Dict]):
    science_vars = []
    for var in collection_variable_list:
        if 'VariableType' in var['umm'] and 'SCIENCE_VARIABLE' == var['umm']['VariableType']:
            science_vars.append(var)
    return science_vars


def get_variable_name_from_umm_json(variable_umm_json) -> str:
    if 'umm' in variable_umm_json and 'Name' in variable_umm_json['umm']:
        name = variable_umm_json['umm']['Name']

        return "/".join(name.strip("/").split('/')[1:]) if '/' in name else name

    return ""


def create_smaller_bounding_box(east, west, north, south, scale_factor):
    """
    Create a smaller bounding box from the given east, west, north, and south values.

    Parameters:
    - east (float): Easternmost longitude.
    - west (float): Westernmost longitude.
    - north (float): Northernmost latitude.
    - south (float): Southernmost latitude.
    - scale_factor (float): Scale factor to determine the size of the smaller bounding box.

    Returns:
    - smaller_bounding_box (tuple): (east, west, north, south) of the smaller bounding box.
    """

    # Validate input
    if east <= west or north <= south:
        raise ValueError("Invalid input values for longitude or latitude.")

    # Calculate the center of the original bounding box
    center_lon = (east + west) / 2
    center_lat = (north + south) / 2

    # Calculate the new coordinates for the smaller bounding box
    smaller_east = (east - center_lon) * scale_factor + center_lon
    smaller_west = (west - center_lon) * scale_factor + center_lon
    smaller_north = (north - center_lat) * scale_factor + center_lat
    smaller_south = (south - center_lat) * scale_factor + center_lat

    return smaller_east, smaller_west, smaller_north, smaller_south


def get_lat_lon_var_names(dataset: xarray.Dataset, file_to_subset: str, collection_variable_list: List[Dict], collection_concept_id: str):
    # Try getting it from UMM-Var first
    lat_var_json, lon_var_json, _ = get_coordinate_vars_from_umm(collection_variable_list)
    lat_var_name = get_variable_name_from_umm_json(lat_var_json)
    lon_var_name = get_variable_name_from_umm_json(lon_var_json)

    if lat_var_name and lon_var_name:
        return lat_var_name, lon_var_name

    logging.warning("Unable to find lat/lon vars in UMM-Var")

    # If that doesn't work, try using cf-xarray to infer lat/lon variable names
    try:
        latitude = [lat for lat in dataset.cf.coordinates['latitude']
                         if lat.lower() in VALID_LATITUDE_VARIABLE_NAMES][0]
        longitude = [lon for lon in dataset.cf.coordinates['longitude']
                         if lon.lower() in VALID_LONGITUDE_VARIABLE_NAMES][0]
        return latitude, longitude
    except:
        logging.warning("Unable to find lat/lon vars using cf_xarray")

    # If that still doesn't work, try using l2ss-py directly
    try:
        # file not able to be flattened unless locally downloaded
        filename = f'my_copy_file_{collection_concept_id}.nc'
        shutil.copy(file_to_subset, filename)
        nc_dataset = netCDF4.Dataset(filename, mode='r+')
        # flatten the dataset
        nc_dataset_flattened = podaac.subsetter.group_handling.transform_grouped_dataset(nc_dataset, filename)

        args = {
                'decode_coords': False,
                'mask_and_scale': False,
                'decode_times': False
                }
        
        with xarray.open_dataset(
            xarray.backends.NetCDF4DataStore(nc_dataset_flattened),
            **args
            ) as flat_dataset:
                # use l2ss-py to find lat and lon names
                lat_var_names, lon_var_names = podaac.subsetter.subset.compute_coordinate_variable_names(flat_dataset)

        os.remove(filename)
        if lat_var_names and lon_var_names:
            lat_var_name = lat_var_names.split('__')[-1] if isinstance(lat_var_names, str) else lat_var_names[0].split('__')[-1]
            lon_var_name = lon_var_names.split('__')[-1] if isinstance(lon_var_names, str) else lon_var_names[0].split('__')[-1]
            return lat_var_name, lon_var_name
        
    except ValueError:
        logging.warning("Unable to find lat/lon vars using l2ss-py")

    # Still no dice, try using the 'units' variable attribute
    for coord_name, coord in dataset.coords.items():
        if 'units' not in coord.attrs:
            continue
        if coord.attrs['units'] == 'degrees_north' and lat_var_name is None:
            lat_var_name = coord_name
        if coord.attrs['units'] == 'degrees_east' and lon_var_name is None:
            lon_var_name = coord_name
    if lat_var_name and lon_var_name:
        return lat_var_name, lon_var_name
    else:
        logging.warning("Unable to find lat/lon vars using 'units' attribute")

    # Out of options, fail the test because we couldn't determine lat/lon variables
    pytest.fail(f"Unable to find latitude and longitude variables.")

def find_variable(ds, var_name):
    try:
        var_ds = ds[var_name]
    except KeyError:
        var_ds = ds.get(var_name.rsplit("/", 1)[-1], None)
    return var_ds

def walk_netcdf_groups(subsetted_filepath, lat_var_name):

    with netCDF4.Dataset(subsetted_filepath) as f:
        group_list = []
        subsetted_ds_new = None
        
        def group_walk(groups, nc_d, current_group):
            nonlocal subsetted_ds_new
            
            # Check if the top group has lat or lon variable
            if lat_var_name in nc_d.variables:
                subsetted_ds_new = xarray.open_dataset(subsetted_filepath, group=current_group, decode_times=False)
                return True  # Found latitude variable
            
            # Loop through the groups in the current layer
            for g in groups:
                # End the loop if we've already found latitude
                if subsetted_ds_new:
                    break
                
                # Check if the current group has latitude variable
                if lat_var_name in nc_d.groups[g].variables:
                    lat_group = '/'.join(group_list + [g])
                    try:
                        subsetted_ds_new = xarray.open_dataset(subsetted_filepath, group=lat_group, decode_times=False)
                        
                        # Add a science variable to the dataset if other groups are present
                        if nc_d.groups[g].groups:
                            data_group = next((v for v in nc_d.groups[g].groups if 'time' not in v.lower()), None)
                            if data_group:
                                g_data = f"{lat_group}/{data_group}"
                                subsetted_ds_data = xarray.open_dataset(subsetted_filepath, group=g_data, decode_times=False)
                                sci_var = list(subsetted_ds_data.variables.keys())[0]
                                subsetted_ds_new['science_test'] = subsetted_ds_data[sci_var]
                    except Exception as ex:
                        print(f"Error while processing group {g}: {ex}")
                        continue
                    
                    break  # Exit the loop once we found the latitude group

                # Recursively call the function on the nested groups
                if nc_d.groups[g].groups:
                    group_list.append(g)
                    found = group_walk(nc_d.groups[g].groups, nc_d.groups[g], g)
                    group_list.pop()  # Clean up after recursion
                    if found:
                        break

        group_walk(f.groups, f, '')
        
    return subsetted_ds_new

@pytest.mark.timeout(1200)
def test_spatial_subset(collection_concept_id, env, granule_json, collection_variables,
                        harmony_env, tmp_path: pathlib.Path, bearer_token_manager, skip_spatial, overrides):
    test_spatial_subset.__doc__ = f"Verify spatial subset for {collection_concept_id} in {env}"

    collection_overrides = resolve_overrides(overrides, collection_concept_id)
    if not should_run_generic("spatial", collection_overrides):
        pytest.skip(f"Generic spatial disabled for {collection_concept_id}")

    custom_tests = find_custom_tests(collection_concept_id)
    if custom_tests.get("collection") and not collection_overrides.get("also_run_generic", False):
        pytest.skip(f"Custom collection tests present; skipping generic spatial for {collection_concept_id}")
    if custom_tests.get("provider") and collection_overrides.get("replace_generic", False):
        pytest.skip(f"Custom provider tests present; skipping generic spatial for {collection_concept_id}")

    if collection_overrides.get("skip_spatial"):
        pytest.skip(f"Spatial override skip for {collection_concept_id}")
    if collection_concept_id in skip_spatial and not collection_overrides.get("force_spatial"):
        pytest.skip(f"Known collection to skip for spatial testing {collection_concept_id}")

    logging.info("Using granule %s for test", granule_json['meta']['concept-id'])

    # Compute a box that is smaller than the granule extent bounding box
    north, south, east, west = get_bounding_box(granule_json)
    spatial_scale = collection_overrides.get("spatial_bbox_scale", DEFAULT_SPATIAL_BBOX_SCALE)
    east, west, north, south = create_smaller_bounding_box(east, west, north, south, float(spatial_scale))

    start_time = granule_json['umm']["TemporalExtent"]["RangeDateTime"]["BeginningDateTime"]
    end_time = granule_json['umm']["TemporalExtent"]["RangeDateTime"]["EndingDateTime"]
    
    request_bbox = harmony.BBox(w=west, s=south, e=east, n=north)
    request_collection = harmony.Collection(id=collection_concept_id)
    harmony_request = harmony.Request(collection=request_collection, spatial=request_bbox,
                                      granule_id=[granule_json['meta']['concept-id']])
    subsetted_filepath = None
    for attempt in range(2):
        try:
            harmony_client = harmony.Client(env=harmony_env, token=bearer_token_manager(refresh=(attempt == 1)))
            logging.info("Sending harmony request %s", harmony_client.request_as_url(harmony_request))

            # Submit harmony request and download result
            job_id = harmony_client.submit(harmony_request)
            logging.info("Submitted harmony job %s", job_id)
            harmony_client.wait_for_processing(job_id, show_progress=False)
            for filename in [file_future.result()
                             for file_future
                             in harmony_client.download_all(job_id, directory=f'{tmp_path}', overwrite=True)]:
                logging.info(f'Downloaded: %s', filename)
                subsetted_filepath = pathlib.Path(filename)
            break
        except Exception as e:
            if attempt == 0 and is_auth_error(e):
                logging.info("Auth error while running Harmony request. Refreshing token and retrying once.")
                continue
            raise

    # Verify spatial subset worked
    subsetted_ds = xarray.open_dataset(subsetted_filepath, decode_times=False)
    group = None
    # Try to read group in file
    lat_var_name, lon_var_name = get_lat_lon_var_names(subsetted_ds, subsetted_filepath, collection_variables, collection_concept_id)
    lat_var_name = lat_var_name.split('/')[-1]
    lon_var_name = lon_var_name.split('/')[-1]

    subsetted_ds_new = walk_netcdf_groups(subsetted_filepath, lat_var_name)

    assert lat_var_name and lon_var_name

    var_ds = None
    msk = None

    science_vars = get_science_vars(collection_variables)
    if science_vars:
        for var in science_vars:
            science_var_name = var['umm']['Name']
            var_ds = find_variable(subsetted_ds_new, science_var_name)
            if var_ds is not None:
                try:
                    msk = np.logical_not(np.isnan(var_ds.data.squeeze()))
                    break
                except Exception:
                    continue
        else:
            var_ds, msk = None, None
    else:
        for science_var_name in subsetted_ds_new.variables:
            if (str(science_var_name) not in lat_var_name and 
                str(science_var_name) not in lon_var_name and 
                'time' not in str(science_var_name)):

                var_ds = find_variable(subsetted_ds_new, science_var_name)
                if var_ds is not None:
                    try:
                        msk = np.logical_not(np.isnan(var_ds.data.squeeze()))
                        break
                    except Exception:
                        continue
        else:
            var_ds, msk = None, None

    if var_ds is None or msk is None:
        logging.warning("Unable to find a science variable to use. Proceeding to test longitude and latitude only.")
        llat = subsetted_ds_new[lat_var_name]
        llon = subsetted_ds_new[lon_var_name]
    else:
        try:
            msk = np.logical_not(np.isnan(var_ds.data.squeeze()))
            llat = subsetted_ds_new[lat_var_name].where(msk)
            llon = subsetted_ds_new[lon_var_name].where(msk)
        except ValueError:
            llat = subsetted_ds_new[lat_var_name]
            llon = subsetted_ds_new[lon_var_name]

    lat_max = llat.max()
    lat_min = llat.min()

    lon_min = llon.min()
    lon_max = llon.max()

    lon_min = (lon_min + 180) % 360 - 180
    lon_max = (lon_max + 180) % 360 - 180

    lat_var_fill_value = subsetted_ds_new[lat_var_name].encoding.get('_FillValue')
    lon_var_fill_value = subsetted_ds_new[lon_var_name].encoding.get('_FillValue')

    partial_pass = False
    if lat_var_fill_value:
        if (lat_max <= north or np.isclose(lat_max, north)) and (lat_min >= south or np.isclose(lat_min, south)):
            logging.info("Successful Latitude subsetting")
        elif np.isnan(lat_max) and np.isnan(lat_min):
            logging.info("Partial Lat Success - no Data")
            partial_pass = True
        else:
            assert False

    if lon_var_fill_value:
        if (lon_max <= east or np.isclose(lon_max, east)) and (lon_min >= west or np.isclose(lon_min, west)):
            logging.info("Successful Longitude subsetting")
        elif np.isnan(lon_max) and np.isnan(lon_min):
            logging.info("Partial Lon Success - no Data")
            partial_pass = True
        else:
            assert False

    if partial_pass:
        valid_lon = np.isfinite(llon) & (llon != lon_var_fill_value)
        valid_lat = np.isfinite(llat) & (llat != lat_var_fill_value)

        if not np.any(valid_lon) or not np.any(valid_lat):
            pytest.fail("No data in lon and lat")

@pytest.mark.timeout(1200)
def test_temporal_subset(collection_concept_id, env, granule_json, collection_variables,
                        harmony_env, tmp_path: pathlib.Path, bearer_token_manager, skip_temporal, overrides):
    test_spatial_subset.__doc__ = f"Verify temporal subset for {collection_concept_id} in {env}"

    collection_overrides = resolve_overrides(overrides, collection_concept_id)
    if not should_run_generic("temporal", collection_overrides):
        pytest.skip(f"Generic temporal disabled for {collection_concept_id}")

    custom_tests = find_custom_tests(collection_concept_id)
    if custom_tests.get("collection") and not collection_overrides.get("also_run_generic", False):
        pytest.skip(f"Custom collection tests present; skipping generic temporal for {collection_concept_id}")
    if custom_tests.get("provider") and collection_overrides.get("replace_generic", False):
        pytest.skip(f"Custom provider tests present; skipping generic temporal for {collection_concept_id}")

    if collection_overrides.get("skip_temporal"):
        pytest.skip(f"Temporal override skip for {collection_concept_id}")
    if collection_concept_id in skip_temporal and not collection_overrides.get("force_temporal"):
        pytest.skip(f"Known collection to skip for temporal testing {collection_concept_id}")

    start_time = granule_json['umm']["TemporalExtent"]["RangeDateTime"]["BeginningDateTime"]
    end_time = granule_json['umm']["TemporalExtent"]["RangeDateTime"]["EndingDateTime"]
    temporal_fraction = collection_overrides.get("temporal_fraction", DEFAULT_TEMPORAL_FRACTION)
    temporal_subset = get_middle_temporal_extent(start_time, end_time, float(temporal_fraction))
    
    request_collection = harmony.Collection(id=collection_concept_id)
    harmony_request = harmony.Request(collection=request_collection,
                                      granule_id=[granule_json['meta']['concept-id']],
                                      temporal=temporal_subset)
    for attempt in range(2):
        try:
            harmony_client = harmony.Client(env=harmony_env, token=bearer_token_manager(refresh=(attempt == 1)))
            logging.info("Sending harmony request %s", harmony_client.request_as_url(harmony_request))

            # Submit harmony request and download result
            job_id = harmony_client.submit(harmony_request)
            logging.info("Submitted harmony job %s", job_id)
            harmony_client.wait_for_processing(job_id, show_progress=False)
            assert harmony_client.status(job_id).get('status') == "successful"
            break
        except Exception as e:
            if attempt == 0 and is_auth_error(e):
                logging.info("Auth error while running Harmony request. Refreshing token and retrying once.")
                continue
            raise
