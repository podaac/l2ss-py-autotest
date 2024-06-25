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

from requests.auth import HTTPBasicAuth

import cmr

VALID_LATITUDE_VARIABLE_NAMES = ['lat', 'latitude']
VALID_LONGITUDE_VARIABLE_NAMES = ['lon', 'longitude']

assert cfxr, "cf_xarray adds extensions to xarray on import"
GROUP_DELIM = '__'

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
        return harmony.config.Environment.PROD


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
def granule_json(collection_concept_id: str, cmr_mode: str, bearer_token: str, request_session) -> dict:
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
    cmr_url = f"{cmr_mode}granules.umm_json?collection_concept_id={collection_concept_id}&sort_key=-start_date&page_size=1"

    response_json = request_session.get(cmr_url, headers={'Authorization': f'Bearer {bearer_token}'}).json()

    if 'items' in response_json and len(response_json['items']) > 0:
        return response_json['items'][0]
    elif cmr_mode == cmr.CMR_UAT:
        pytest.skip(f"No granules found for UAT collection {collection_concept_id}. CMR search used was {cmr_url}")
    elif cmr_mode == cmr.CMR_OPS:
        pytest.fail(f"No granules found for OPS collection {collection_concept_id}. CMR search used was {cmr_url}")


@pytest.fixture(scope="function")
def original_granule_localpath(granule_json: dict, tmp_path, bearer_token: str,
                               request_session: requests.Session) -> pathlib.Path:
    urls = granule_json['umm']['RelatedUrls']

    def download_file(url):
        local_filename = tmp_path.joinpath(f"{granule_json['meta']['concept-id']}_original_granule.nc")
        response = request_session.get(url, headers={'Authorization': f'Bearer {bearer_token}'}, stream=True)
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


def get_half_temporal_extent(start: str, end: str):
    # Convert the input string dates to datetime objects (account for the 'Z' in the strings)
    start_dt = datetime.strptime(start, '%Y-%m-%dT%H:%M:%S.%fZ')
    end_dt = datetime.strptime(end, '%Y-%m-%dT%H:%M:%S.%fZ')
    
    # Calculate the total duration
    total_duration = end_dt - start_dt
    
    # Calculate the half duration
    half_duration = total_duration / 2
    
    # Calculate the quarter duration (half of the half duration)
    quarter_duration = half_duration / 2
    
    # Determine the new start and end times
    new_start_dt = start_dt + quarter_duration
    new_end_dt = end_dt - quarter_duration
    
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


def get_lat_lon_var_names(dataset: xarray.Dataset, file_to_subset: str, collection_variable_list: List[Dict]):
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
        shutil.copy(file_to_subset, 'my_copy_file.nc')
        nc_dataset = netCDF4.Dataset('my_copy_file.nc', mode='r+')
        # flatten the dataset
        nc_dataset_flattened = podaac.subsetter.group_handling.transform_grouped_dataset(nc_dataset, 'my_copy_file.nc')

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

        os.remove('my_copy_file.nc')
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

@pytest.mark.timeout(600)
def test_spatial_subset(collection_concept_id, env, granule_json, collection_variables,
                        harmony_env, tmp_path: pathlib.Path, bearer_token):
    test_spatial_subset.__doc__ = f"Verify spatial subset for {collection_concept_id} in {env}"

    logging.info("Using granule %s for test", granule_json['meta']['concept-id'])

    # Compute a box that is smaller than the granule extent bounding box
    north, south, east, west = get_bounding_box(granule_json)
    east, west, north, south = create_smaller_bounding_box(east, west, north, south, .95)

    start_time = granule_json['umm']["TemporalExtent"]["RangeDateTime"]["BeginningDateTime"]
    end_time = granule_json['umm']["TemporalExtent"]["RangeDateTime"]["EndingDateTime"]
    
    # Build harmony request
    harmony_client = harmony.Client(env=harmony_env, token=bearer_token)
    request_bbox = harmony.BBox(w=west, s=south, e=east, n=north)
    request_collection = harmony.Collection(id=collection_concept_id)
    harmony_request = harmony.Request(collection=request_collection, spatial=request_bbox,
                                      granule_id=[granule_json['meta']['concept-id']])

    logging.info("Sending harmony request %s", harmony_client.request_as_url(harmony_request))

    # Submit harmony request and download result
    job_id = harmony_client.submit(harmony_request)
    logging.info("Submitted harmony job %s", job_id)
    harmony_client.wait_for_processing(job_id, show_progress=True)
    subsetted_filepath = None
    for filename in [file_future.result()
                     for file_future
                     in harmony_client.download_all(job_id, directory=f'{tmp_path}', overwrite=True)]:
        logging.info(f'Downloaded: %s', filename)
        subsetted_filepath = pathlib.Path(filename)

    # Verify spatial subset worked
    subsetted_ds = xarray.open_dataset(subsetted_filepath, decode_times=False)
    group = None
    # Try to read group in file
    lat_var_name, lon_var_name = get_lat_lon_var_names(subsetted_ds, subsetted_filepath, collection_variables)
    lat_var_name = lat_var_name.split('/')[-1]
    lon_var_name = lon_var_name.split('/')[-1]

    with netCDF4.Dataset(subsetted_filepath) as f:
        group_list = []
        def group_walk(groups, nc_d, current_group):
            global subsetted_ds_new
            subsetted_ds_new = None
            # check if the top group has lat or lon variable
            if lat_var_name in list(nc_d.variables.keys()):
                subsetted_ds_new = subsetted_ds
            else:
                # if not then we'll need to keep track of the group layers
                group_list.append(current_group)

            # loop through the groups in the current layer
            for g in groups:
                # end the loop if we've already found latitude
                if subsetted_ds_new:
                    break
                # check if the groups have latitude, define the dataset and end the loop if found
                if lat_var_name in list(nc_d.groups[g].variables.keys()):
                    group_list.append(g)
                    g = '/'.join(group_list)
                    subsetted_ds_new = xarray.open_dataset(subsetted_filepath, group=g, decode_times=False)
                    break
                # recall the function on a group that has groups in it and didn't find latitude
                # this is going 'deeper' into the groups
                if len(list(nc_d.groups[g].groups.keys())) > 0:
                    group_walk(nc_d.groups[g].groups, nc_d.groups[g], g)
                else:
                    continue

        group_walk(f.groups, f, '')

    assert lat_var_name and lon_var_name

    var_ds = None
    msk = None

    if science_vars := get_science_vars(collection_variables):
        for idx, value in enumerate(science_vars):
            science_var_name = science_vars[idx]['umm']['Name']
            try:
                var_ds = subsetted_ds_new[science_var_name]
                msk = np.logical_not(np.isnan(var_ds.data.squeeze()))
                break
            except Exception:
                try:
                    # if the variable couldn't be found because the name includes a group, e.g.,
                    # `geolocation/relative_azimuth_angle`,
                    # then try to access the variable after removing the group name.
                    var_ds = subsetted_ds_new[science_var_name.rsplit("/", 1)[-1]]
                    msk = np.logical_not(np.isnan(var_ds.data.squeeze()))
                    break
                except Exception:
                    var_ds = None
                    msk = None

        if var_ds is None and msk is None:
            pytest.fail(f"Unable to find variable from umm-v to use as science variable.")

    else:
        # Can't find a science var in UMM-V, just pick one

        science_var_name = next(iter([v for v in subsetted_ds_new.variables if
                                    str(v) not in lat_var_name and str(v) not in lon_var_name and 'time' not in str(v)]))

        var_ds = subsetted_ds_new[science_var_name]

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

    if lat_var_fill_value:
        if (lat_max <= north or np.isclose(lat_max, north)) and (lat_min >= south or np.isclose(lat_min, south)):
            logging.info("Successful Latitude subsetting")
        elif np.isnan(lat_max) and np.isnan(lat_min):
            logging.info("Partial Lat Success - no Data")
        else:
            assert False

    if lon_var_fill_value:
        if (lon_max <= east or np.isclose(lon_max, east)) and (lon_min >= west or np.isclose(lon_min, west)):
            logging.info("Successful Longitude subsetting")
        elif np.isnan(lon_max) and np.isnan(lon_min):
            logging.info("Partial Lon Success - no Data")
        else:
            assert False

@pytest.mark.timeout(600)
def test_temporal_subset(collection_concept_id, env, granule_json, collection_variables,
                        harmony_env, tmp_path: pathlib.Path, bearer_token):
    test_spatial_subset.__doc__ = f"Verify spatial subset for {collection_concept_id} in {env}"

    logging.info("Using granule %s for test", granule_json['meta']['concept-id'])

    start_time = granule_json['umm']["TemporalExtent"]["RangeDateTime"]["BeginningDateTime"]
    end_time = granule_json['umm']["TemporalExtent"]["RangeDateTime"]["EndingDateTime"]
    temporal_subset = get_half_temporal_extent(start_time, end_time)
    
    # Build harmony request
    harmony_client = harmony.Client(env=harmony_env, token=bearer_token)
    request_collection = harmony.Collection(id=collection_concept_id)
    harmony_request = harmony.Request(collection=request_collection,
                                      granule_id=[granule_json['meta']['concept-id']],
                                      temporal=temporal_subset)

    logging.info("Sending harmony request %s", harmony_client.request_as_url(harmony_request))

    # Submit harmony request and download result
    job_id = harmony_client.submit(harmony_request)
    logging.info("Submitted harmony job %s", job_id)

    harmony_client.wait_for_processing(job_id, show_progress=True)
    assert harmony_client.status(job_id).get('status') == "successful"
