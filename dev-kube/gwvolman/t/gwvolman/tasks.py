"""A set of WT related Girder tasks."""
import os
import shutil
import socket
import json
import time
import tempfile
import textwrap
import docker
import subprocess
from docker.errors import DockerException
import girder_client
from .tasks_factory import TasksFactory

import logging
try:
    from urlparse import urlparse
except ImportError:
    from urllib.parse import urlparse
from girder_worker.utils import girder_job
from girder_worker.app import app
# from girder_worker.plugins.docker.executor import _pull_image
from .utils import \
    HOSTDIR, REGISTRY_USER, REGISTRY_PASS, \
    new_user, _safe_mkdir, _get_api_key, \
    _get_container_config, _launch_container, _get_user_and_instance, \
    DEPLOYMENT
from .publish import publish_tale
from .constants import GIRDER_API_URL, InstanceStatus, ENABLE_WORKSPACES, \
    DEFAULT_USER, DEFAULT_GROUP, MOUNTPOINTS

flavor = 'docker'
if 'TASKS_FLAVOR' in os.environ:
    flavor = os.environ['TASKS_FLAVOR']

tasksCls = TasksFactory().getTasks(flavor)


@girder_job(title='Create Tale Data Volume')
@app.task(bind=True)
def create_volume(self, instanceId: str):
    """Create a mountpoint and compose WT-fs."""
    return tasksCls.create_volume(self, instanceId)


@girder_job(title='Spawn Instance')
@app.task(bind=True)
def launch_container(self, payload):
    """Launch a container using a Tale object."""
    return tasksCls.launch_container(self, payload)


@girder_job(title='Update Instance')
@app.task(bind=True)
def update_container(self, instanceId, **kwargs):
    return tasksCls.update_container(self, instanceId, kwarks)


@girder_job(title='Shutdown Instance')
@app.task(bind=True)
def shutdown_container(self, instanceId):
    """Shutdown a running Tale."""
    return tasksCls.shutdown_container(self, instanceId)


@girder_job(title='Remove Tale Data Volume')
@app.task(bind=True)
def remove_volume(self, instanceId):
    """Unmount WT-fs and remove mountpoint."""
    return tasksCls.remove_volume(self, instanceId)


@girder_job(title='Build WT Image')
@app.task
def build_image(image_id, repo_url, commit_id):
    """Build docker image from WT Image object and push to a registry."""
    return tasksCls.build_image(image_id, repo_url, commit_id)


@girder_job(title='Publish Tale')
@app.task
def publish(item_ids,
            tale,
            dataone_node,
            dataone_auth_token,
            girder_token,
            userId,
            prov_info,
            license_id):
    """
    Publish a Tale to DataONE.

    :param item_ids: A list of item ids that are in the package
    :param tale: The tale id
    :param dataone_node: The DataONE member node endpoint
    :param dataone_auth_token: The user's DataONE JWT
    :param girder_token: The user's girder token
    :param userId: The user's ID
    :param prov_info: Additional information included in the tale yaml
    :param license_id: The spdx of the license used
    :type item_ids: list
    :type tale: str
    :type dataone_node: str
    :type dataone_auth_token: str
    :type girder_token: str
    :type userId: str
    :type prov_info: dict
    :type license_id: str
    """
    return tasksCls.publish_tale(item_ids, tale, dataone_node, 
                                 dataone_auth_token, girder_token, userId, 
                                 prov_info, license_id)


@girder_job(title='Import Tale')
@app.task(bind=True)
def import_tale(self, lookup_kwargs, tale_kwargs, spawn=True):
    """Create a Tale provided a url for an external data and an image Id.

    Currently, this task only handles importing raw data. In the future, it
    should also allow importing serialized Tales.
    """
    return tasksCls.import_tale(self, lookup_kwarks, tale_kwargs, spawn)
