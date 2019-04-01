import logging
import hashlib
import io
import xml.etree.cElementTree as ET

from .constants import \
    ExtraFileNames, \
    license_text, \
    file_descriptions

from .utils import \
    strip_html_tags, \
    check_pid, \
    get_directory, \
    get_file_item, \
    compute_md5


from d1_common.types import dataoneTypes
from d1_common import const as d1_const
from d1_common.resource_map import createSimpleResourceMap


"""
Methods that are responsible for handling metadata generation and parsing
belong here.
"""


def create_resource_map(resmap_pid, eml_pid, file_pids):
    """
    Creates a resource map for the package.

    :param resmap_pid: The pid od the resource map
    :param eml_pid: The pid of the science metadata
    :param file_pids: The pids for each file in the package
    :type resmap_pid: str
    :type eml_pid: str
    :type file_pids: list
    :return: The resource map for the package
    :rtype: bytes
    """

    res_map = createSimpleResourceMap(resmap_pid, eml_pid, file_pids)
    # createSimpleResourceMap returns type d1_common.resource_map.ResourceMap
    return res_map.serialize()


def create_entity(root, name, description):
    """
    Create an otherEntity section
    :param root: The parent element
    :param name: The name of the object
    :param description: The description of the object
    :type root: xml.etree.ElementTree.Element
    :type name: str
    :type description: str
    :return: An entity section
    :rtype: xml.etree.ElementTree.Element
    """
    entity = ET.SubElement(root, 'otherEntity')
    ET.SubElement(entity, 'entityName').text = name
    if description:
        ET.SubElement(entity, 'entityDescription').text = description
    return entity


def create_physical(other_entity_section, name, size):
    """
    Creates a `physical` section.
    :param other_entity_section: The super-section
    :param name: The name of the object
    :param size: The size in bytes of the object
    :type other_entity_section: xml.etree.ElementTree.Element
    :type name: str
    :type size: str
    :return: The physical section
    :rtype: xml.etree.ElementTree.Element
    """
    physical = ET.SubElement(other_entity_section, 'physical')
    ET.SubElement(physical, 'objectName').text = name
    size_element = ET.SubElement(physical, 'size')
    size_element.text = str(size)
    size_element.set('unit', 'bytes')
    return physical


def create_format(object_format, physical_section):
    """
    Creates a `dataFormat` field in the EML to describe the format
     of the object
    :param object_format: The format of the object
    :param physical_section: The etree element defining a `physical` EML section
    :type object_format: str
    :type physical_section: xml.etree.ElementTree.Element
    :return: None
    """
    data_format = ET.SubElement(physical_section, 'dataFormat')
    externally_defined = ET.SubElement(data_format, 'externallyDefinedFormat')
    ET.SubElement(externally_defined, 'formatName').text = object_format


def create_intellectual_rights(dataset_element, license_id):
    """
    :param dataset_element: The xml element that defines the `dataset`
    :param license_id: The ID of the license
    :type dataset_element: xml.etree.ElementTree.Element
    :type license_id: str
    :return: None
    """
    intellectual_rights = ET.SubElement(dataset_element, 'intellectualRights')
    section = ET.SubElement(intellectual_rights, 'section')
    para = ET.SubElement(section, 'para')
    ET.SubElement(para, 'literalLayout').text = \
        license_text.get(license_id, '')


def add_object_record(root, name, description, size, object_format):
    """
    Add a section to the EML that describes an object.
    :param root: The root entity
    :param name: The name of the object
    :param description: The object's description
    :param size: The size of the object
    :param object_format: The format type
    :type root: xml.etree.ElementTree.Element
    :type name: str
    :type description: str
    :type size: str
    :type object_format: str
    :return: None
    """
    entity_section = create_entity(root, name, strip_html_tags(description))
    physical_section = create_physical(entity_section,
                                       name,
                                       size)
    create_format(object_format, physical_section)
    ET.SubElement(entity_section, 'entityType').text = 'dataTable'


def set_user_name(root, first_name, last_name):
    """
    Creates a section in the EML that describes a user's name.
    :param root: The parent XML element
    :param first_name: The user's first name
    :param last_name: The user's last name
    :type root: xml.etree.ElementTree.Element
    :type first_name: str
    :type last_name: str
    :return: None
    """
    individual_name = ET.SubElement(root, 'individualName')
    ET.SubElement(individual_name, 'givenName').text = first_name
    ET.SubElement(individual_name, 'surName').text = last_name


def set_user_contact(root, user_id, email):
    """
    Creates a section that describes the contact and owner
    :param root: The parent XML element
    :param user_id: The user's ID
    :param email: The user's email
    :type root: xml.etree.ElementTree.Element
    :type user_id: str
    :type email: str
    :return: None
    """
    ET.SubElement(root, 'electronicMailAddress').text = email
    users_id = ET.SubElement(root, 'userId')
    users_id.text = user_id
    users_id.set('directory', get_directory(user_id))


def create_minimum_eml(tale,
                       user,
                       item_ids,
                       eml_pid,
                       file_sizes,
                       license_id,
                       user_id,
                       gc):
    """
    Creates a bare minimum EML record for a package. Note that the
    ordering of the xml elements matters.

    :param tale: The tale that is being packaged.
    :param user: The user that hit the endpoint
    :param item_ids: A list of the item ids of the objects that are going to be packaged
    :param eml_pid: The PID for the eml document. Assume that this is the package doi
    :param file_sizes: When we upload files that are not in the girder system (ie not
     files or items) we need to manually pass their size in. Use this dict to do that.
    :param license_id: The ID of the license
    :param user_id: The user's user id from the JWT
    girder items/files
    :param gc: The girder client
    :type tale: wholetale.models.tale
    :type user: girder.models.user
    :type item_ids: list
    :type eml_pid: str
    :type file_sizes: dict
    :type license_id: str
    :type user_id: str
    :return: The EML as as string of bytes
    :rtype: bytes
    """

    """
    Check that we're able to assign a first, last, and email to the record.
    If we aren't throw an exception and let the user know. We'll also check that
    the user has a userID from their JWT.
    """
    last_name = user.get('lastName', None)
    first_name = user.get('firstName', None)
    email = user.get('email', None)

    if any((None for x in [last_name, first_name, email])):
        return 'Unable to find your name or email address. Please ensure ' \
               'you have authenticated with DataONE.'

    logging.debug('Creating EML Record')
    # Create the namespace
    ns = ET.Element('eml:eml')
    ns.set('xmlns:eml', "eml://ecoinformatics.org/eml-2.1.1")
    ns.set('xsi:schemaLocation', "eml://ecoinformatics.org/eml-2.1.1 eml.xsd")
    ns.set('xmlns:stmml', "http://www.xml-cml.org/schema/stmml-1.1")
    ns.set('xmlns:xsi', "http://www.w3.org/2001/XMLSchema-instance")
    ns.set('scope', "system")
    ns.set('system', "knb")
    ns.set('packageId', eml_pid)

    """
    Create a `dataset` field, and assign the title to
     the name of the Tale. The DataONE Quality Engine
     prefers to have titles with at least 7 words.
    """
    dataset = ET.SubElement(ns, 'dataset')
    ET.SubElement(dataset, 'title').text = str(tale.get('title', ''))

    """
    Create a `creator` section, using the information in the
     `model.user` object to provide values.
    """
    creator = ET.SubElement(dataset, 'creator')
    set_user_name(creator, first_name, last_name)
    set_user_contact(creator, user_id, email)

    # Create a `description` field, but only if the Tale has a description.
    description = tale.get('description', str())
    if description is not str():
        abstract = ET.SubElement(dataset, 'abstract')
        ET.SubElement(abstract, 'para').text = strip_html_tags(str(description))

    # Add a section for the license file
    create_intellectual_rights(dataset, license_id)

    # Add a section for the contact
    contact = ET.SubElement(dataset, 'contact')
    set_user_name(contact, first_name, last_name)
    set_user_contact(contact, user_id, email)

    # Add a <otherEntity> block for each object
    for item_id in item_ids:

        # Create the record for the object
        item = gc.getItem(item_id)
        file = get_file_item(item_id, gc)
        add_object_record(dataset,
                          item['name'],
                          item.get('description', ''),
                          item['size'],
                          file['mimeType'])

    # Add a section for the tale.yml file
    logging.debug('Adding tale.yaml to EML')
    file_sizes.get('tale_yaml')
    description = file_descriptions[ExtraFileNames.tale_config]
    name = ExtraFileNames.tale_config
    object_format = 'application/x-yaml'
    add_object_record(dataset,
                      name,
                      description,
                      file_sizes.get('tale_yaml'),
                      object_format)

    # Add a section for the license file
    if file_sizes.get('license'):
        logging.debug('Adding LICENSE to EML')
        description = file_descriptions[ExtraFileNames.license_filename]
        name = ExtraFileNames.license_filename
        object_format = 'text/plain'
        add_object_record(dataset,
                          name,
                          description,
                          file_sizes.get('license'),
                          object_format)

    # Add a section for the repository file
    if file_sizes.get('repository'):
        logging.debug('Adding repository.tar.gz to EML')
        description = file_descriptions[ExtraFileNames.environment_file]
        name = ExtraFileNames.environment_file
        object_format = 'application/tar+gzip'
        add_object_record(dataset,
                          name,
                          description,
                          file_sizes.get('repository'),
                          object_format)
    """
    Emulate the behavior of ElementTree.tostring in Python 3.6.0
     Write the contents to a stream and then return its content.
     The Python 3.4 version of ElementTree.tostring doesn't allow for
     `xml_declaration` to be set, so make a direct call to
     ElementTree.write, passing xml_declaration in.
    """
    stream = io.BytesIO()
    ET.ElementTree(ns).write(file_or_filename=stream,
                             encoding='UTF-8',
                             xml_declaration=True,
                             method='xml',
                             short_empty_elements=True)

    return stream.getvalue()


def generate_system_metadata(pid,
                             format_id,
                             file_object,
                             name,
                             rights_holder,
                             is_file=False,
                             size=None):
    """
    Generates a metadata document describing the file_object.

    :param pid: The pid that the object will have
    :param format_id: The format of the object (e.g text/csv)
    :param file_object: The object that is being described
    :param name: The name of the object being described
    :param rights_holder: The owner of this object
    :param is_file: A bool set to true if file_object is an iterator
    :param size: The size of the file
    :type pid: str
    :type format_id: str
    :type file_object: unicode or girder.models.file
    :type name: str
    :type rights_holder: str
    :type is_file: Bool
    :type size: int
    :return: The metadata describing file_object
    :rtype: d1_common.types.generated.dataoneTypes_v2_0.SystemMetadata
    """

    md5 = hashlib.md5()
    if is_file:
        # If it's a local file, get the md5 of it
        md5 = compute_md5(file_object)
    else:
        # Check that the file_object is unicode, attempt to convert it if it's a str
        if not isinstance(file_object, bytes):
            if isinstance(file_object, str):
                file_object = file_object.encode("utf-8")
        md5.update(file_object)
        size = len(file_object)
    md5 = md5.hexdigest()
    sys_meta = populate_sys_meta(pid,
                                 format_id,
                                 size,
                                 md5,
                                 name,
                                 rights_holder)
    return sys_meta


def populate_sys_meta(pid, format_id, size, md5, name, rights_holder):
    """
    Fills out the system metadata object with the needed properties

    :param pid: The pid of the system metadata document
    :param format_id: The format of the document being described
    :param size: The size of the document that is being described
    :param md5: The md5 hash of the document being described
    :param name: The name of the file
    :param rights_holder: The owner of this object
    :type pid: str
    :type format_id: str
    :type size: int
    :type md5: str
    :type name: str
    :type rights_holder: str
    :return: The populated system metadata document
    """

    pid = check_pid(pid)
    sys_meta = dataoneTypes.systemMetadata()
    sys_meta.identifier = pid
    sys_meta.formatId = format_id
    sys_meta.size = size
    sys_meta.rightsHolder = rights_holder
    sys_meta.checksum = dataoneTypes.checksum(str(md5))
    sys_meta.checksum.algorithm = 'MD5'
    sys_meta.accessPolicy = generate_public_access_policy()
    sys_meta.fileName = name
    return sys_meta


def generate_public_access_policy():
    """
    Creates the access policy for the system metadata.
     Note that the permission is set to 'read'.

    :return: The access policy
    :rtype: d1_common.types.generated.dataoneTypes_v1.AccessPolicy
    """

    access_policy = dataoneTypes.accessPolicy()
    access_rule = dataoneTypes.AccessRule()
    access_rule.subject.append(d1_const.SUBJECT_PUBLIC)
    permission = dataoneTypes.Permission('read')
    access_rule.permission.append(permission)
    access_policy.append(access_rule)
    return access_policy
