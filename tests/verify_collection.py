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


# Helper function to read a single CSV file and return a set of skip entries
def read_skip_list(csv_file):
    with open(csv_file, newline='') as f:
        reader = csv.reader(f)
        return {row[0].strip() for row in reader}


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
def bearer_token(env: str, request_session: requests.Session) -> str:
    url = f"https://{'uat.' if env == 'uat' else ''}urs.earthdata.nasa.gov/api/users/find_or_create_token"

    try:
        # Make the request with the Base64-encoded Authorization header
        resp = request_session.post(
            url,
            auth=HTTPBasicAuth(os.environ['CMR_USER'], os.environ['CMR_PASS'])
        )

        # Check for successful response
        if resp.status_code == 200:
            response_content = resp.json()
            return response_content.get('access_token')

    except Exception as e:
        logging.warning(f"Error getting the token (status code {resp.status_code}): {e}", exc_info=True)

    # Skip the test if no token is found
    pytest.skip("Unable to get bearer token from EDL")


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
        pytest.fail(f"No granules found for UAT collection {collection_concept_id}. CMR search used was {cmr_url}")
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
        pytest.fail(f"Unable to find download URL for {granule_json['meta']['concept-id']}")


@pytest.fixture(scope="function")
def collection_variables(cmr_mode, collection_concept_id, env, bearer_token):
    collection_query = cmr.queries.CollectionQuery(mode=cmr_mode)
    variable_query = cmr.queries.VariableQuery(mode=cmr_mode)

    collection_res = collection_query.concept_id(collection_concept_id).token(bearer_token).get()[0]
    collection_associations = collection_res.get("associations")
    variable_concept_ids = collection_associations.get("variables")

    if variable_concept_ids is None:
        pytest.fail(f'There are no umm-v associated with this collection in {env}')

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
    # Adjust the format to handle cases without fractional seconds
    try:
        start_dt = datetime.strptime(start, '%Y-%m-%dT%H:%M:%S.%fZ')
    except ValueError:
        start_dt = datetime.strptime(start, '%Y-%m-%dT%H:%M:%SZ')
    
    try:
        end_dt = datetime.strptime(end, '%Y-%m-%dT%H:%M:%S.%fZ')
    except ValueError:
        end_dt = datetime.strptime(end, '%Y-%m-%dT%H:%M:%SZ')
    
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
                        harmony_env, tmp_path: pathlib.Path, bearer_token, skip_spatial):
    test_spatial_subset.__doc__ = f"Verify spatial subset for {collection_concept_id} in {env}"

    if collection_concept_id in skip_spatial:
        pytest.skip(f"Known collection to skip for spatial testing {collection_concept_id}")

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
    harmony_client.wait_for_processing(job_id, show_progress=False)
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
                        harmony_env, tmp_path: pathlib.Path, bearer_token, skip_temporal):
    test_spatial_subset.__doc__ = f"Verify temporal subset for {collection_concept_id} in {env}"

    if collection_concept_id in skip_temporal:
        pytest.skip(f"Known collection to skip for temporal testing {collection_concept_id}")

    # Skip all ob-daac temporal test, ob-daac data have no time variables
    if "OB_CLOUD" not in collection_concept_id:
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

        harmony_client.wait_for_processing(job_id, show_progress=False)
        assert harmony_client.status(job_id).get('status') == "successful"
