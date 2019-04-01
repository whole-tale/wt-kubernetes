# -*- coding: utf-8 -*-
# Copyright (c) 2016, Data Exploration Lab
# Distributed under the terms of the Modified BSD License.

"""A set of helper routines for WT related tasks."""

from collections import namedtuple
import os
import random
import re
import string
import uuid
import logging
import jwt
import hashlib

try:
    from urlparse import urlparse
except ImportError:
    from urllib.parse import urlparse
import docker

from .constants import \
    DataONELocations, MOUNTPOINTS

DOCKER_URL = os.environ.get("DOCKER_URL", "unix://var/run/docker.sock")
HOSTDIR = os.environ.get("HOSTDIR", "/host")
MAX_FILE_SIZE = os.environ.get("MAX_FILE_SIZE", 200)
DOMAIN = os.environ.get('DOMAIN', 'dev.wholetale.org')
TRAEFIK_ENTRYPOINT = os.environ.get("TRAEFIK_ENTRYPOINT", "http")
REGISTRY_USER = os.environ.get('REGISTRY_USER', 'fido')
REGISTRY_PASS = os.environ.get('REGISTRY_PASS')

MOUNTS = {}
RETRIES = 5
container_name_pattern = re.compile('tmp\.([^.]+)\.(.+)\Z')

PooledContainer = namedtuple('PooledContainer', ['id', 'path', 'host'])
ContainerConfig = namedtuple('ContainerConfig', [
    'image', 'command', 'mem_limit', 'cpu_shares',
    'container_port', 'container_user', 'target_mount',
    'url_path', 'environment'
])

SIZE_NOTATION_RE = re.compile("^(\d+)([kmg]?b?)$", re.IGNORECASE)
SIZE_TABLE = {
    '': 1, 'b': 1,
    'k': 1024, 'kb': 1024,
    'm': 1024 ** 2, 'mb': 1024 ** 2,
    'g': 1024 ** 3, 'gb': 1024 ** 3
}


def size_notation_to_bytes(size):
    if isinstance(size, int):
        return size
    match = SIZE_NOTATION_RE.match(size)
    if match:
        val, suffix = match.groups()
        return int(val) * SIZE_TABLE[suffix.lower()]
    raise ValueError


class Deployment(object):
    """Container for WT-specific docker stack deployment configuration.

    This class allows to read and store configuration of services in a WT
    deployment. It's meant to be used as a singleton across gwvolman.
    """

    _dashboard_url = None
    _girder_url = None
    _registry_url = None
    _traefik_network = None

    def __init__(self):
        self.docker_client = docker.from_env(version='1.28')

    @property
    def traefik_network(self):
        """str: Name of the overlay network used by traefik for ingress."""
        if self._traefik_network is None:
            service = self.docker_client.services.get('wt_dashboard')
            self._traefik_network = \
                service.attrs['Spec']['Labels']['traefik.docker.network']
        return self._traefik_network

    @property
    def dashboard_url(self):
        """str: Dashboard's public url."""
        if self._dashboard_url is None:
            self._dashboard_url = self.get_host_from_traefik_rule('wt_dashboard')
        return self._dashboard_url

    @property
    def girder_url(self):
        """str: Girder's public url."""
        if self._girder_url is None:
            self._girder_url = self.get_host_from_traefik_rule('wt_girder')
        return self._girder_url

    @property
    def registry_url(self):
        """str: Docker Registry's public url."""
        if self._registry_url is None:
            self._registry_url = self.get_host_from_traefik_rule('wt_registry')
        return self._registry_url

    def get_host_from_traefik_rule(self, service_name):
        """Infer service's hostname from traefik frontend rule label."""
        service = self.docker_client.services.get(service_name)
        rule = service.attrs['Spec']['Labels']['traefik.frontend.rule']
        return 'https://' + rule.split(':')[-1].split(',')[0].strip()


DEPLOYMENT = Deployment()


def sample_with_replacement(a, size):
    """Get a random path."""
    return "".join([random.SystemRandom().choice(a) for x in range(size)])


def new_user(size):
    """Get a random path."""
    return sample_with_replacement(string.ascii_letters + string.digits, size)


def _safe_mkdir(dest):
    try:
        os.mkdir(dest)
    except OSError as e:
        if e.errno != 17:
            raise
        logging.warn("Failed to mkdir {}".format(dest))
        pass


def _get_api_key(gc):
    api_key = None
    for key in gc.get('/api_key'):
        if key['name'] == 'tmpnb' and key['active']:
            api_key = key['key']

    if api_key is None:
        api_key = gc.post('/api_key',
                          data={'name': 'tmpnb', 'active': True})['key']
    return api_key


def _get_user_and_instance(girder_client, instanceId):
    user = girder_client.get('/user/me')
    if user is None:
        logging.warn("Bad gider token")
        raise ValueError
    instance = girder_client.get('/instance/' + instanceId)
    return user, instance


def get_env_with_csp(config):
    '''Ensure that environment in container config has CSP_HOSTS setting.

    This method handles 3 cases:
        * No 'environment' in config -> return ['CSP_HOSTS=...']
        * 'environment' in config, but no 'CSP_HOSTS=...' -> append
        * 'environment' in config and has 'CSP_HOSTS=...' -> replace

    '''
    csp = "CSP_HOSTS='self' {}".format(DEPLOYMENT.dashboard_url)
    try:
        env = config['environment']
        original_csp = next((_ for _ in env if _.startswith('CSP_HOSTS')), None)
        if original_csp:
            env[env.index(original_csp)] = csp  # replace
        else:
            env.append(csp)
    except KeyError:
        env = [csp]
    return env


def _get_container_config(gc, tale):
    if tale is None:
        container_config = {}  # settings['container_config']
    else:
        image = gc.get('/image/%s' % tale['imageId'])
        tale_config = image['config'] or {}
        if tale['config']:
            tale_config.update(tale['config'])

        try:
            mem_limit = size_notation_to_bytes(tale_config.get('memLimit', '2g'))
        except (ValueError, TypeError):
            mem_limit = 2 * 1024 ** 3
        container_config = ContainerConfig(
            command=tale_config.get('command'),
            container_port=tale_config.get('port'),
            container_user=tale_config.get('user'),
            cpu_shares=tale_config.get('cpuShares'),
            environment=get_env_with_csp(tale_config),
            image=urlparse(DEPLOYMENT.registry_url).netloc + '/' + tale['imageId'],
            mem_limit=mem_limit,
            target_mount=tale_config.get('targetMount'),
            url_path=tale_config.get('urlPath')
        )
    return container_config


def _launch_container(volumeName, nodeId, container_config):

    token = uuid.uuid4().hex
    # command
    if container_config.command:
        rendered_command = \
            container_config.command.format(
                base_path='', port=container_config.container_port,
                ip='0.0.0.0', token=token)
    else:
        rendered_command = None

    if container_config.url_path:
        rendered_url_path = \
            container_config.url_path.format(token=token)
    else:
        rendered_url_path = ''

    logging.info('config = ' + str(container_config))
    logging.info('command = ' + str(rendered_command))
    cli = docker.from_env(version='1.28')
    cli.login(username=REGISTRY_USER, password=REGISTRY_PASS,
              registry=DEPLOYMENT.registry_url)
    # Fails with: 'starting container failed: error setting
    #              label on mount source ...: read-only file system'
    # mounts = [
    #     docker.types.Mount(type='volume', source=volumeName, no_copy=True,
    #                        target=container_config.target_mount)
    # ]

    # FIXME: get mountPoint
    source_mount = '/var/lib/docker/volumes/{}/_data'.format(volumeName)
    mounts = []
    for path in MOUNTPOINTS:
        source = os.path.join(source_mount, path)
        target = os.path.join(container_config.target_mount, path)
        mounts.append(
            docker.types.Mount(type='bind', source=source, target=target)
        )
    host = 'tmp-{}'.format(new_user(12).lower())

    # https://github.com/containous/traefik/issues/2582#issuecomment-354107053
    endpoint_spec = docker.types.EndpointSpec(mode="vip")

    service = cli.services.create(
        container_config.image,
        command=rendered_command,
        labels={
            'traefik.port': str(container_config.container_port),
            'traefik.enable': 'true',
            'traefik.frontend.rule': 'Host:{}.{}'.format(host, DOMAIN),
            'traefik.docker.network': DEPLOYMENT.traefik_network,
            'traefik.frontend.passHostHeader': 'true',
            'traefik.frontend.entryPoints': TRAEFIK_ENTRYPOINT
        },
        env=container_config.environment,
        mode=docker.types.ServiceMode('replicated', replicas=1),
        networks=[DEPLOYMENT.traefik_network],
        name=host,
        mounts=mounts,
        endpoint_spec=endpoint_spec,
        constraints=['node.id == {}'.format(nodeId)],
        resources=docker.types.Resources(mem_limit=container_config.mem_limit)
    )

    # Wait for the server to launch within the container before adding it
    # to the pool or serving it to a user.
    # _wait_for_server(host_ip, host_port, path) # FIXME

    url = '{proto}://{host}.{domain}/{path}'.format(
        proto=TRAEFIK_ENTRYPOINT, host=host, domain=DOMAIN,
        path=rendered_url_path)

    return service, {'url': url}


def get_file_item(item_id, gc):
    """
    Gets the file out of an item.

    :param item_id: The item that has the file inside
    :param gc: The girder client
    :type: item_id: str
    :return: The file object or None
    :rtype: girder.models.file
    """
    file_generator = gc.listFile(item_id)
    try:
        return next(file_generator)
    except StopIteration as e:
        return None


def is_dataone_url(url):
    """
    Checks if a url has dataone in it
    :param url: The url in question
    :return: True if it does, False otherwise
    """

    res = url.find('dataone.org')
    if res is not -1:
        return True
    else:
        return False


def is_dev_url(url):
    """
    Determines whether the object at the URL is on the NCEAS
    Development network
    :param url: URL to the object
    :type url: str
    :return: True of False, depending on whether it's on the dev network
    :rtype: bool
    """
    parsed_url = urlparse(url).netloc
    parsed_dev_mn = urlparse(DataONELocations.dev_cn).netloc

    if parsed_url == parsed_dev_mn:
        return True
    return False


def is_in_network(url, network):
    """
    Checks to see if the url shares the same netlocation as network
    :param url: The URL to a data object
    :param network: The url of the member node being checke
    :return: True or False
    """
    parsed_url = urlparse(url).netloc
    parsed_network = urlparse(network).netloc
    base_dev_mn = urlparse(DataONELocations.dev_mn).netloc
    base_dev_cn = urlparse(DataONELocations.dev_cn).netloc

    if parsed_network == base_dev_mn:
        # Then we're in NCEAS Development
        # The resolve address is through the membernode in this case
        if parsed_url == base_dev_cn:
            # Then the object is in network
            return True
        else:
            # Then the object is outside network
            return False

    else:
        # Otherwise we're on DataONE

        base_dev_cn = urlparse(DataONELocations.prod_cn).netloc

        if parsed_url == base_dev_cn:
            # Then the object is in network
            return True
        else:
            # Then the object is outside network
            return False


def check_pid(pid):
    """
    Check that a pid is of type str. Pids are generated as uuid4, and this
    check is done to make sure the programmer has converted it to a str before
    attempting to use it with the DataONE client.

    :param pid: The pid that is being checked
    :type pid: str, int
    :return: Returns the pid as a str, or just the pid if it was already a str
    :rtype: str
    """

    if not isinstance(pid, str):
        return str(pid)
    else:
        return pid


def get_remote_url(item_id, gc):
    """
    Checks if a file has a link url and returns the url if it does. This is less
     restrictive than thecget_dataone_url in that we aren't restricting the link
      to a particular domain.

    :param item_id: The id of the item
    :param gc: The girder client
    :return: The url that points to the object
    :rtype: str or None
    """

    file = get_file_item(item_id, gc)
    if file is None:
        file_error = 'Failed to find the file with ID {}'.format(item_id)
        logging.warning(file_error)
        raise ValueError(file_error)
    url = file.get('linkUrl')
    if url is not None:
        return url


def get_dataone_package_url(repository, pid):
    """
    Given a repository url and a pid, construct a url that should
     be the package's landing page.

    :param repository: The repository that the package is on
    :param pid: The package pid
    :return: The package landing page
    """
    if repository in DataONELocations.prod_cn:
        return str('https://search.dataone.org/#view/'+pid)
    elif repository in DataONELocations.dev_mn:
        return str('https://dev.nceas.ucsb.edu/#view/'+pid)


def extract_user_id(jwt_token):
    """
    Takes a JWT and extracts the 'userId` field. This is used
    as the package's owner and contact.
    :param jwt_token: The decoded JWT
    :type jwt_token: str
    :return: The ORCID ID
    :rtype: str, None if failure
    """
    jwt_token = jwt.decode(jwt_token, verify=False)
    user_id = jwt_token.get('userId', None)
    if user_id is not None:
        if is_orcid_id(user_id):
            return make_url_https(user_id)
    return user_id


def is_orcid_id(user_id):
    """
    Checks whether a string is a link to an ORCID account
    :param user_id: The string that may contain the ORCID account
    :type user_id: str
    :return: True/False if it is or isn't
    :rtype: bool
    """
    return bool(user_id.find('orcid.org'))


def esc(value):
    """
    Escape a string so it can be used in a Solr query string
    :param value: The string that will be escaped
    :type value: str
    :return: The escaped string
    :rtype: str
    """
    return urlparse.quote_plus(value)


def strip_html_tags(string):
    """
    Removes HTML tags from a string
    :param string: The string with HTML
    :type string: str
    :return: The string without HTML
    :rtype: str
    """
    return re.sub('<[^<]+?>', '', string)


def get_directory(user_id):
    """
    Returns the directory that should be used in the EML

    :param user_id: The user ID
    :type user_id: str
    :return: The directory name
    :rtype: str
    """
    if is_orcid_id(user_id):
        return "https://orcid.org"
    return "https://cilogon.org"


def make_url_https(url):
    """
    Given an http url, return it as https

    :param url: The http url
    :type url: str
    :return: The url as https
    :rtype: str
    """
    parsed = urlparse(url)
    return parsed._replace(scheme="https").geturl()


def get_file_md5(file_object, gc):
    """
    Computes the md5 of a file on the Girder filesystem.

    :param file_object: The file object that will be hashed
    :param gc: The girder client
    :type file_object: girder.models.file
    :return: Returns an updated md5 object. Returns None if it fails
    :rtype: md5
    """

    file = gc.downloadFileAsIterator(file_object['_id'])
    try:
        md5 = compute_md5(file)
    except Exception as e:
        logging.warning('Error: {}'.format(e))
        raise ValueError('Failed to download and md5 a remote file. {}'.format(e))
    return md5


def compute_md5(file):
    """
    Takes an file handle and computes the md5 of it. This uses duck typing
    to allow for any file handle that supports .read. Note that it is left to the
    caller to close the file handle and to handle any exceptions

    :param file: An open file handle that can be read
    :return: Returns an updated md5 object. Returns None if it fails
    :rtype: md5
    """
    md5 = hashlib.md5()
    while True:
        buf = file.read(8192)
        if not buf:
            break
        md5.update(buf)
    return md5


def filter_items(item_ids, gc):
    """
    Take a list of item ids and determine whether it:
       1. Exists on the local file system
       2. Exists on DataONE
       3. Is linked to a remote location other than DataONE
    :param item_ids: A list of items to be processed
    :param gc: The girder client
    :type item_ids: list
    :return: A dictionary of lists for each file location
    For example,
     {'dataone': ['uuid:123456', 'doi.10x501'],
     'remote_objects: ['url1', 'url2'],
     local: [file_obj1, file_obj2]}
    :rtype: dict
    """

    # Holds item_ids for DataONE objects
    dataone_objects = list()
    # Holds item_ids for files not in DataONE
    remote_objects = list()
    # Holds file dicts for local objects
    local_objects = list()
    # Holds item_ids for local files
    local_items = list()

    for item_id in item_ids:
        # Check if it points do a dataone objbect
        url = get_remote_url(item_id, gc)
        if url is not None:
            if is_dataone_url(url):
                dataone_objects.append(item_id)
                continue

            """
            If there is a url, and it's not pointing to a DataONE resource, then assume
            it's pointing to an external object
            """
            logging.debug('Adding remote object')
            remote_objects.append(item_id)
            continue

        # If the file wasn't linked to a remote location, then it must exist locally. This
        # is a list of girder.models.File objects
        logging.debug('Adding local object')
        local_objects.append(get_file_item(item_id, gc))
        local_items.append(item_id)

    return {'dataone': dataone_objects,
            'remote': remote_objects,
            'local_files': local_objects,
            'local_items': local_items}


def find_initial_pid(path):
    """
    Extracts the pid from an arbitrary path to a DataOne object.
    Supports:
       - HTTP & HTTPS
       - The MetacatUI landing page (#view)
       - The D1 v2 Object URI (/object)
       - The D1 v2 Resolve URI (/resolve)

    :param path:
    :type path: str
    :return: The object's pid, or the original path if one wasn't found
    :rtype: str
    """

    # http://blog.crossref.org/2015/08/doi-regular-expressions.html
    doi_regex = re.compile('(10.\d{4,9}/[-._;()/:A-Z0-9]+)', re.IGNORECASE)
    doi = doi_regex.search(path)
    if re.search(r'^http[s]?:\/\/search.dataone.org\/#view\/', path):
        return re.sub(
            r'^http[s]?:\/\/search.dataone.org\/#view\/', '', path)
    elif re.search(r'\Ahttp[s]?:\/\/cn[a-z\-\d\.]*\.dataone\.org\/cn\/v\d\/[a-zA-Z]+\/.+\Z', path):
        return re.sub(
            r'\Ahttp[s]?:\/\/cn[a-z\-\d\.]*\.dataone\.org\/cn\/v\d\/[a-zA-Z]+\/', '', path)
    if re.search(r'^http[s]?:\/\/dev.nceas.ucsb.edu\/#view\/', path):
        return re.sub(
            r'^http[s]?:\/\/dev.nceas.ucsb.edu\/#view\/', '', path)
    if re.search(r'resolve', path):
        return path.split("resolve/", 1)[1]
    elif doi is not None:
        return 'doi:{}'.format(doi.group())
    else:
        return path
