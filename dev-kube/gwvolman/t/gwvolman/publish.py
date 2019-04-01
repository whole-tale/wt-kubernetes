import io
import tempfile
import logging

try:
    from urllib.request import urlopen
except ImportError:
    from urllib2 import urlopen
from shutil import copyfileobj
import uuid
import requests
import yaml as yaml
import os
import girder_client


from d1_client.mnclient_2_0 import MemberNodeClient_2_0
from d1_common.types.exceptions import DataONEException

from .utils import \
    check_pid, \
    get_file_item, \
    compute_md5, \
    extract_user_id, \
    filter_items, \
    get_dataone_package_url

from .dataone_metadata import \
    generate_system_metadata, \
    create_minimum_eml, \
    create_resource_map

from .constants import \
    ExtraFileNames, \
    license_files, \
    GIRDER_API_URL, \
    API_VERSION


def create_upload_eml(tale,
                      client,
                      user,
                      item_ids,
                      license_id,
                      user_id,
                      file_sizes,
                      gc):
    """
    Creates the EML metadata document along with an additional metadata document
    and uploads them both to DataONE. A pid is created for the EML document, and is
    returned so that the resource map can reference it at a later time.

    :param tale: The tale that is being described
    :param client: The client to DataONE
    :param user: The user that is requesting this action
    :param item_ids: The ids of the items that have been uploaded to DataONE
    :param license_id: The ID of the license
    :param user_id: The user that owns this resource
    :param file_sizes: We need to sometimes account for non-data files
     (like tale.yml) .The size needs to be in the EML record so pass them
      in here. The size should be described in bytes
    :param gc: The girder client
    :type tale: wholetale.models.tale
    :type client: MemberNodeClient_2_0
    :type user: girder.models.user
    :type item_ids: list
    :type license_id: str
    :type user_id: str
    :type file_sizes: dict
    :return: pid of the EML document
    :rtype: str
    """

    # Create the EML metadata
    eml_pid = str(uuid.uuid4())
    eml_doc = create_minimum_eml(tale,
                                 user,
                                 item_ids,
                                 eml_pid,
                                 file_sizes,
                                 license_id,
                                 user_id,
                                 gc)
    # Create the metadata describing the EML document
    meta = generate_system_metadata(pid=eml_pid,
                                    format_id='eml://ecoinformatics.org/eml-2.1.1',
                                    file_object=eml_doc,
                                    name='science_metadata.xml',
                                    rights_holder=user_id)
    # meta is type d1_common.types.generated.dataoneTypes_v2_0.SystemMetadata
    # Upload the EML document with its metadata
    upload_file(client=client,
                pid=eml_pid,
                file_object=io.BytesIO(eml_doc),
                system_metadata=meta)
    return eml_pid


def create_external_object_structure(external_files, user, gc):
    """
    Creates a JSON file that describes a remote which has the following format
     {file_name : {'url': url, 'md5': md5}
     We'll want to compute the md5, so we have to save the file
     temporarily.

    :param external_files: A list of files that exist outside WholeTale
    :param user: The user publishing the tale
    :param gc: The girder client
    :type external_files: list
    :type user: girder.mnodels.user
    :return: A dictionary that lists each remote file with its md5
    :rtype: dict
    """

    reference_file = dict()

    for item in external_files:
        """
        Get the underlying file object from the supplied item id.
        We'll need the `linkUrl` field to determine where it is pointing to.
        """
        file = get_file_item(item, gc)
        if file is not None:
            url = file.get('linkUrl', None)
            if url is not None:
                """
                Create a temporary file object which will eventually hold the contents
                of the remote object.
                """
                with tempfile.NamedTemporaryFile() as temp_file:
                    try:
                        src = urlopen(url)
                        # Copy the response into the temporary file
                        copyfileobj(src, temp_file)

                    except requests.exceptions.HTTPError:
                        # if we fail to download the file, exit
                        return 'There was a problem downloading an external file, {} ' \
                               'located at {}.'.format(file['name'], url)

                    # Get the md5 of the file
                    md5 = compute_md5(temp_file)
                    digest = md5.hexdigest()

                    """
                    Create dictionary entries for the file. We key off of the file name,
                    and store the url and md5 with it.
                    """
                    url_entry = {'url': url}
                    md5_entry = {'md5': digest}
                    reference_file[file['name']] = url_entry, md5_entry

    return reference_file


def create_dataone_client(mn_base_url, auth_token):
    """
    Creates and returns a member node client

    :param mn_base_url: The url of the member node endpoint
    :param auth_token: The auth token for the user that is using the client
    Should be of the form {"headers": { "Authorization": "Bearer <TOKEN>}}
    :type mn_base_url: str
    :type auth_token: dict
    :return: A client for communicating with a DataONE node
    :rtype: MemberNodeClient_2_0
    """
    return MemberNodeClient_2_0(mn_base_url, **auth_token)


def upload_file(client, pid, file_object, system_metadata):
    """
    Uploads two files to a DataONE member node. The first is an object, which is just a data file.
    The second is a metadata file describing the file object.

    :param client: A client for communicating with a member node
    :param pid: The pid of the data object
    :param file_object: The file object that will be uploaded to the member node
    :param system_metadata: The metadata object describing the file object
    :type client: MemberNodeClient_2_0
    :type pid: str
    :type file_object: str
    :type system_metadata: d1_common.types.generated.dataoneTypes_v2_0.SystemMetadata
    """

    pid = check_pid(pid)
    try:
        client.create(pid, file_object, system_metadata)
    except DataONEException as e:
        return 'Error uploading file to DataONE. {0}'.format(str(e))


def create_paths_structure(item_ids, gc):
    """
    Creates a file that lists the path that each item is located at.
    :param item_ids: A list of items that are in the tale
    :param gc: The girder client
    :type item_ids: list
    :return: The dict representing the file structure
    :rtype: dict
    """

    """
    We'll use a dict structure to hold the file contents during creation for
     convenience.
    """
    path_file = dict()

    for item_id in item_ids:
        item = gc.getItem(item_id)
        path = gc.get('resource/{}/path?type=item'.format(item_id))
        path_file[item['name']] = path

    return path_file


def create_tale_info_structure(tale):
    """
    Any miscellaneous information about the tale can be added here.
    :param tale: The tale that is being published
    :type tale: wholetale.models.Tale
    :return: A dictionary of tale information
    :rtype: dict
    """

    # We'll store the information as a dictionary
    tale_info = dict()
    tale_info['version'] = API_VERSION
    tale_info['identifier'] = str(tale['_id'])
    tale_info['metadata'] = 'Metadata: science_metadata.xml'
    tale_info['category'] = str(tale.get('category', 'None'))
    tale_info['format'] = str(tale.get('format', 'None'))
    tale_info['config'] = str(tale.get('config', 'None'))
    return tale_info


def create_upload_resmap(res_pid, eml_pid, obj_pids, client, rights_holder):
    """
    Creates a resource map describing a package and uploads it to DataONE. The
    resource map can be thought of as the glue that holds a package together.

    In order to do this, the following steps are taken.
        1. Create the resource map
        2. Create the metadata document describing the resource map
        3. Upload the pair to DataONE

    :param res_pid: The pid for the resource map
    :param eml_pid: The pid for the metadata document
    :param obj_pids: A list of the pids for each object that was uploaded to DataONE;
     A list of pids that the resource map is documenting.
    :param client: The client to the DataONE member node
    :param rights_holder: The owner of this object
    :type res_pid: str
    :type eml_pid: str
    :type obj_pids: list
    :type client: MemberNodeClient_2_0
    :type rights_holder: str
    :return: None
    """

    res_map = create_resource_map(res_pid, eml_pid, obj_pids)
    # To view the contents of res_map, call d1_common.xml.serialize_to_transport()
    meta = generate_system_metadata(res_pid,
                                    format_id='http://www.openarchives.org/ore/terms',
                                    file_object=res_map,
                                    name=str(),
                                    rights_holder=rights_holder)

    upload_file(client=client,
                pid=res_pid,
                file_object=io.BytesIO(res_map),
                system_metadata=meta)


def create_upload_tale_yaml(tale,
                            remote_objects,
                            item_ids,
                            user,
                            client,
                            prov_info,
                            rights_holder,
                            gc):
    """
    The yaml content is represented with Python dicts, and then dumped to
     the yaml object.
    :param tale: The tale that is being published
    :param remote_objects: A list of objects that are registered external to WholeTale
    :param item_ids: A list of all of the ids of the files that are being uploaded
    :param user: The user performing the actions
    :param client: The client that interfaces DataONE
    :param prov_info: A dictionary of additional parameters for the file. This information
    is gathered in the UI and passed through the REST endpoint.
    :param rights_holder: The owner of this object
    :param gc: The girder client
    :type tale: wholetale.models.Tale
    :type remote_objects: list
    :type item_ids: list
    :type user: girder.models.User
    :type client: MemberNodeClient_2_0
    :type prov_info: dict
    :type rights_holder: str
    :return: The pid and the size of the file
    :rtype: tuple
    """

    # Create the dict that has general information about the package
    tale_info = create_tale_info_structure(tale)

    # Create the dict that holds the file paths
    file_paths = dict()
    file_paths['paths'] = create_paths_structure(item_ids, gc)

    # Create the dict that tracks externally defined objects, if applicable
    external_files = dict()
    if len(remote_objects) > 0:
        external_files['external files'] = create_external_object_structure(remote_objects, user, gc)

    # Append all of the information together
    yaml_file = dict(tale_info)
    yaml_file.update(file_paths)

    if bool(external_files):
        yaml_file.update(external_files)
    if prov_info:
        yaml_file.update(prov_info)
    # Transform the file into yaml from the dict structure
    yaml_file = yaml.dump(yaml_file, default_flow_style=False)

    # Create a pid for the file
    pid = str(uuid.uuid4())
    # Create system metadata for the file
    meta = generate_system_metadata(pid=pid,
                                    format_id='text/plain',
                                    file_object=yaml_file,
                                    name=ExtraFileNames.tale_config,
                                    rights_holder=rights_holder)
    # Upload the file
    upload_file(client=client,
                pid=pid,
                file_object=io.StringIO(yaml_file),
                system_metadata=meta)

    # Return the pid
    return pid, len(yaml_file)


def upload_license_file(client, license_id, rights_holder):
    """
    Upload a license file to DataONE.

    :param client: The client that interfaces DataONE
    :param license_id: The ID of the license (see `ExtraFileNames` in constants)
    :param rights_holder: The owner of this object
    :type client: MemberNodeClient_2_0
    :type license_id: str
    :type rights_holder: str
    :return: The pid and size of the license file
    """
    # Holds the license text
    license_text = str()
    PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))
    ROOT_DIR = os.path.dirname(PACKAGE_DIR)
    # Path to the license file
    license_path = os.path.join(ROOT_DIR, 'gwvolman', 'licenses',
                                license_files[license_id])
    try:
        license_length = os.path.getsize(license_path)
        with open(license_path) as f:
            license_text = f.read()
    except IOError:
        logging.warning('Failed to open license file')
        return None, 0

    # Create a pid for the file
    pid = str(uuid.uuid4())
    # Create system metadata for the file
    meta = generate_system_metadata(pid=pid,
                                    format_id='text/plain',
                                    file_object=license_text,
                                    name=ExtraFileNames.license_filename,
                                    rights_holder=rights_holder)
    # Upload the file
    upload_file(client=client, pid=pid, file_object=license_text, system_metadata=meta)

    # Return the pid and length of the file
    return pid, license_length


def create_upload_object_metadata(client, file_object, rights_holder, gc):
    """
    Takes a file that exists on the filesystem and
        1. Creates metadata describing it
        2. Uploads the file_object with the metadata to DataONE
        3. Returns a pid that is assigned to file_object so that it can
            be added to the resource map later.

    :param client: The client to the DataONE member node
    :param file_object: The file object that will be uploaded
    :param rights_holder: The owner of this object
    :param gc: The girder client
    :type client: MemberNodeClient_2_0
    :type file_object: girder.models.file
    :type rights_holder: str
    :return: The pid of the object
    :rtype: str
    """

    # PID for the metadata object
    pid = str(uuid.uuid4())
    with tempfile.NamedTemporaryFile() as temp_file:
        gc.downloadFile(file_object['_id'], temp_file.name)
        temp_file.seek(0)
        meta = generate_system_metadata(pid,
                                        format_id=file_object['mimeType'],
                                        file_object=temp_file,
                                        name=file_object['name'],
                                        is_file=True,
                                        rights_holder=rights_holder,
                                        size=file_object['size'])
        temp_file.seek(0)
        upload_file(client=client,
                    pid=pid,
                    file_object=temp_file.read(),
                    system_metadata=meta)
        logging.info('Uploaded file to DataONE, PID {}'.format(pid))
    return pid


def create_upload_repository(tale, client, rights_holder, gc):
    """
    Downloads the repository that's pointed to by the recipe and uploads it to the
    node that `client` points to.
    :param tale: The Tale that is being registered
    :param client: The interface to the member node
    :param rights_holder: The owner of this object
    :param gc: The girder client
    :type tale: girder.models.tale
    :type client: MemberNodeClient_2_0
    :type rights_holder: str
    :return:
    """
    try:
        image = gc.get('/image/{}'.format(tale['imageId']))
        recipe = gc.get('/recipe/{}'.format(image['recipeId']))
        download_url = recipe['url'] + '/tarball/' + recipe['commitId']

        with tempfile.NamedTemporaryFile() as temp_file:
            src = urlopen(download_url)
            try:
                # Copy the response into the temporary file
                copyfileobj(src, temp_file)
                logging.debug('Copied file, size: {}'.format(temp_file.tell()))

            except IOError as e:
                error_msg = 'Error copying environment file to disk. {}'.format(e)
                logging.warning(error_msg)

                # We should stop if we can't upload the repository
                return error_msg
        # Create a pid for the file
            pid = str(uuid.uuid4())
        # Create system metadata for the file
            temp_file.seek(0)
            meta = generate_system_metadata(pid=pid,
                                            format_id='application/tar+gzip',
                                            file_object=temp_file.read(),
                                            name=ExtraFileNames.environment_file,
                                            rights_holder=rights_holder)
            temp_file.seek(0)
            logging.debug('Uploading repository to DataONE')
            upload_file(client=client,
                        pid=pid,
                        file_object=io.BytesIO(temp_file.read()),
                        system_metadata=meta)

            size = os.path.getsize(temp_file.name)
        return pid, size

    except IOError as e:
        logging.debug('Failed to process repository'.format(e))
    return None, 0


def publish_tale(item_ids,
                 taleId,
                 dataone_node,
                 dataone_auth_token,
                 girder_token,
                 userId,
                 prov_info,
                 license_id):
    """
    Handles publishing a tale to DataONE.

    The Item Ids are filtered into where the physical data resides. The possible locations
    are
        1. On DataONE
        2. On dev.nceas.ucsb.edu
        3. On Globus
        4. On Girder
        5. An external HTTP resource

    Information from the Tale structure is used when generating metadata. Information used includes
    the name, description, and ID.

    :param item_ids: A list of item ids that are in the package
    :param taleId: The tale Id
    :param dataone_node: The DataONE member node endpoint
    :param dataone_auth_token: The user's DataONE JWT
    :param girder_token: The user's girder token
    :param userId: The user's ID
    :param prov_info: Additional information included in the tale yaml
    :param license_id: The spdx of the license used
    :type item_ids: list
    :type taleId: str
    :type dataone_node: str
    :type dataone_auth_token: str
    :type girder_token: str
    :type userId: str
    :type prov_info: dict
    :type license_id: str
    :return: The pid of the package's resource map
    :rtype: str
    """
    client = None
    try:
        gc = girder_client.GirderClient(apiUrl=GIRDER_API_URL)
        gc.token = str(girder_token)
    except Exception as e:
        raise ValueError('Error authenticating with Girder {}'.format(e))

    tale = gc.get('/tale/{}/'.format(taleId))
    user = gc.getUser(userId)
    # create_dataone_client can throw DataONEException
    try:
        """
        Create a client object that is used to interface DataONE. This can interact with a
         particular member node by specifying `repository`. The auth_token is the jwt token from
         DataONE.
        """
        logging.debug('Creating the DataONE client')
        client = create_dataone_client(dataone_node, {
            "headers": {
                "Authorization": "Bearer " + dataone_auth_token,
                "Connection": "close"},
            "user_agent": "safari"})
    except DataONEException as e:
        logging.warning('Error creating the DataONE Client: {}'.format(e))
        # We'll want to exit if we can't create the client
        raise ValueError('Failed to establish connection with DataONE. {}'.format(e))

    user_id = extract_user_id(dataone_auth_token)
    if user_id is None:
        # Exit if we can't get the userId from the auth_token
        return 'Failed to process your DataONE credentials. Please' \
               ' ensure you are logged into DataONE.'

    """
    Sort all of the input files based on where they are located,
        1. HTTP resource
        2. DataONE resource
        3. Local filesystem object
    """
    filtered_items = filter_items(item_ids, gc)

    """
    Iterate through the list of objects that are local (ie files without a `linkUrl`
    and upload them to DataONE. The call to create_upload_object_metadata will
     return a pid that describes the object (not the metadata object). We'll save
        this pid so that we can pass it to the resource map.
    """
    local_file_pids = list()
    for file in filtered_items['local_files']:
        logging.debug('Processing local files for DataONE upload')
        local_file_pids.append(create_upload_object_metadata(client, file, user_id, gc))

    logging.debug('Processing Tale YAML file')
    remote_items = filtered_items['remote'] + filtered_items['dataone']

    tale_yaml_pid, tale_yaml_length = create_upload_tale_yaml(tale,
                                                              remote_items,
                                                              item_ids,
                                                              user,
                                                              client,
                                                              prov_info,
                                                              user_id,
                                                              gc)

    """
    Upload the license file
    """
    logging.debug('Uploading the license file')
    license_pid, license_size = upload_license_file(client, license_id, user_id)

    """
    Upload the repository"""
    repository_pid, repository_size = create_upload_repository(tale, client, user_id, gc)

    """
    
    Create an EML document describing the data, and then upload it. Save the
    pid for the resource map.
    """
    file_sizes = {'tale_yaml': tale_yaml_length,
                  'license': license_size,
                  'repository': repository_size}

    """
    Get all of the items, except the ones that were transferred from an external
    source
    """
    eml_items = filtered_items.get('dataone') + \
        filtered_items.get('local_items') + filtered_items.get('remote')

    eml_items = filter(None, eml_items)
    eml_items = list(eml_items)
    logging.debug('Creating DataONE EML record for new Tale')
    eml_pid = create_upload_eml(tale,
                                client,
                                user,
                                eml_items,
                                license_id,
                                extract_user_id(dataone_auth_token),
                                file_sizes,
                                gc)
    # Check eml file status. If it failed, we need to exit and let the user know
    logging.debug('Finished creating DataONE EML record')

    """
    Once all objects are uploaded, create and upload the resource map. This file describes
    the object relations (ie the package). This should be the last file that is uploaded.
    Also filter out any pids that are None, which would have resulted from an error. This
    prevents referencing objects that failed to upload.
    """
    upload_objects = list(local_file_pids + [tale_yaml_pid, license_pid, repository_pid])
    resmap_pid = str(uuid.uuid4())
    logging.debug('Creating DataONE resource map')
    create_upload_resmap(resmap_pid,
                         eml_pid,
                         upload_objects,
                         client,
                         user_id)
    logging.debug('Finished creating DataONE resource map')
    package_url = get_dataone_package_url(dataone_node, resmap_pid)

    return package_url
