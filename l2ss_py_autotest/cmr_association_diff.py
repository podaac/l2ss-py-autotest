
"""
==============
cmr_association_diff.py
==============

Generic command line tool that compares associations of CMR UMM-S
or UMM-T based on a local association.txt

See usage information by running cmr_association_diff.py -h

python cmr_association_diff.py -e uat -t tool -a hitide_uat_associations.txt -p POCLOUD -n hitide
python cmr_association_diff.py -c TL1240538128-POCLOUD -e uat -t tool -a hitide_uat_associations.txt
"""

import json
import argparse
import cmr
import os.path


def pull_concept_id(cmr_env, provider, umm_name, umm_type):
    """
    Uses constructed umm_name, cmr environment and provider string to
    pull concept_id for UMM record on CMR.

    Parameters
    ----------
    cmr_env : string
    provider : string
    umm_name : string
    umm_type: string

    Returns
    -------
    concept_id: string concept id of tool or service
    """

    if umm_type == "tool":
        cmr_query = cmr.queries.ToolQuery(mode=cmr_env)
    elif umm_type == "service":
        cmr_query = cmr.queries.ServiceQuery(mode=cmr_env)

    results = cmr_query.provider(provider).name(umm_name).get()

    if len(results) == 1:  # pylint: disable=R1705
        return results[0].get('concept_id')
    elif len(results) > 1:
        raise Exception(
            f"Provider and Native ID are not unique, more than 1 {umm_type} returned.")
    else:
        # No concept-id exists, UMM record does not exist within CMR
        raise Exception(f"No concept id was found for {umm_name}")


def cmr_environment(env):
    """
    Determine ops or uat url prefix based on env string
    Parameters
    ----------
    env : string uat or ops

    Returns
    -------
    url : string
    """
    # CMR OPS (Operations, also known as Production or PROD)
    if env.lower() == 'ops':  # pylint: disable=R1705
        return cmr.queries.CMR_OPS
    # CMR UAT (User Acceptance Testing)
    elif env.lower() == 'uat':
        return cmr.queries.CMR_UAT
    else:
        raise Exception('CMR environment selection not recognized, select uat or ops.')


def current_association(concept_id, cmr_env, umm_type, token):
    """
    Get list of association concept ids currently in CMR for a service or tool
    Parameters
    ----------
    concept_id : string concept id of umm_type
    cmr_env : string url prefix
    umm_type: string tool or service

    Returns
    -------
    List of string with concept id or exception
    """

    cmr_query = cmr.queries.CollectionQuery(mode=cmr_env)

    if umm_type == "tool":
        results = cmr_query.tool_concept_id(concept_id).token(token).get()
    elif umm_type == "service":
        results = cmr_query.service_concept_id(concept_id).token(token).get()

    return [res.get('id') for res in results]


def parse_args():
    """
    Parses the program arguments
    Returns
    -------
    args
    """

    parser = argparse.ArgumentParser(
        description='Update CMR with latest profile',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )

    parser.add_argument('-c', '--concept_id',
                        help='Concept id of umm to poll',
                        required=False,
                        metavar='')

    parser.add_argument('-e', '--env',
                        help='CMR environment used to pull results from.',
                        required=True,
                        choices=["uat", "ops"],
                        metavar='uat or ops')

    parser.add_argument('-p', '--provider',
                        help='Provider of the umm',
                        required=False,
                        metavar='')

    parser.add_argument('-n', '--umm_name',
                        help='Name of the umm tool or service',
                        required=False,
                        metavar='')

    parser.add_argument('-t', '--type',
                        help='type of umm to poll',
                        choices=["tool", "service"],
                        required=True)

    parser.add_argument('-a', '--assoc',
                        help='Association concept ID or file containing'
                             ' many concept IDs to be associated or dir'
                             ' containing filenames matching concept IDs'
                             ' with UMM provided.',
                        required=True,
                        default=None,
                        metavar='associations.txt')

    parser.add_argument('-o', '--output_file',
                        help='File to output to',
                        required=False,
                        default=None)

    parser.add_argument('-to', '--token',
                        help='CMR UMM token string.',
                        default=None,
                        required=False,
                        metavar='Launchpad token or EDL token')

    args = parser.parse_args()
    return args


def run():
    """
    Run from command line.

    Returns
    -------
    """

    _args = parse_args()

    cmr_env = cmr_environment(_args.env)
    concept_id = _args.concept_id
    umm_type = _args.type
    association_file = _args.assoc

    if _args.token:
        current_token = _args.token
    else:
        current_token = None

    if concept_id is None:
        provider = _args.provider
        umm_name = _args.umm_name
        if provider is None or umm_name is None:
            raise Exception("Need concept id or provider and umm name")
        concept_id = pull_concept_id(cmr_env, provider, umm_name, umm_type)
    else:
        if umm_type == 'tool':
            result = cmr.queries.ToolQuery(mode=cmr_env).concept_id(concept_id).token(current_token).get()
        elif umm_type == 'service':
            result = cmr.queries.ServiceQuery(mode=cmr_env).concept_id(concept_id).token(current_token).get()
        if not result:
            raise Exception(f"Could not retrieve umm {umm_type} using concept_id {concept_id}")

    if os.path.isdir(association_file):
        collections = [os.listdir(association_file)]
    else:
        with open(association_file) as file:  # pylint: disable=W1514
            collections = [x.strip() for x in file.readlines()]

    current_concept_ids = current_association(concept_id, cmr_env, umm_type, current_token)

    new_associations = list(set(current_concept_ids) - set(collections))
    if new_associations:
        if _args.output_file:
            with open(_args.output_file, 'w', encoding='utf-8') as output_file:
                json.dump(new_associations, output_file, ensure_ascii=False, indent=4)
        print(json.dumps(new_associations))


if __name__ == '__main__':
    run()

