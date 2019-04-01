"""Base class for tasks. Contains tasks that are independent of the platform this is deployed on"""
import os
import shutil
import socket
import json
import time
import tempfile
import textwrap
import subprocess
import girder_client

import logging
try:
    from urlparse import urlparse
except ImportError:
    from urllib.parse import urlparse
from girder_worker.utils import girder_job
from girder_worker.app import app
# from girder_worker.plugins.docker.executor import _pull_image
from .publish import publish_tale
from .constants import GIRDER_API_URL, InstanceStatus, ENABLE_WORKSPACES, \
    DEFAULT_USER, DEFAULT_GROUP, MOUNTPOINTS


class TasksBase:
    def __init__(self):
        pass

    def create_volume(self, instanceId: str):
        raise NotImplementedError()

    def launch_container(self, payload):
        raise NotImplementedError()

    def update_container(self, instanceId, **kwargs):
        raise NotImplementedError()

    def shutdown_container(self, instanceId):
        raise NotImplementedError()

    def remove_volume(self, instanceId):
        raise NotImplementedError()

    def build_image(image_id, repo_url, commit_id):
        raise NotImplementedError()

    def publish(item_ids, tale, dataone_node, dataone_auth_token,
                girder_token, userId, prov_info, license_id):
        return publish_tale(item_ids, tale, dataone_node,
                            dataone_auth_token, girder_token,
                            userId, prov_info, license_id)

    def import_tale(self, lookup_kwargs, tale_kwargs, spawn=True):
        """Create a Tale provided a url for an external data and an image Id.

        Currently, this task only handles importing raw data. In the future, it
        should also allow importing serialized Tales.
        """
        if spawn:
            total = 4
        else:
            total = 3

        self.job_manager.updateProgress(
            message='Gathering basic info about the dataset', total=total,
            current=1)
        dataId = lookup_kwargs.pop('dataId')
        try:
            parameters = dict(dataId=json.dumps(dataId))
            parameters.update(lookup_kwargs)
            dataMap = self.girder_client.get(
                '/repository/lookup', parameters=parameters)
        except girder_client.HttpError as resp:
            try:
                message = json.loads(resp.responseText).get('message', '')
            except json.JSONDecodeError:
                message = str(resp)
            errormsg = 'Unable to register \"{}\". Server returned {}: {}'
            errormsg = errormsg.format(dataId[0], resp.status, message)
            raise ValueError(errormsg)

        if not dataMap:
            errormsg = 'Unable to register \"{}\". Source is not supported'
            errormsg = errormsg.format(dataId[0])
            raise ValueError(errormsg)

        self.job_manager.updateProgress(
            message='Registering the dataset in Whole Tale', total=total,
            current=2)
        self.girder_client.post(
            '/dataset/register', parameters={'dataMap': json.dumps(dataMap)})

        # Get resulting folder/item by name
        catalog_path = '/collection/WholeTale Catalog/WholeTale Catalog'
        catalog = self.girder_client.get(
            '/resource/lookup', parameters={'path': catalog_path})
        folders = self.girder_client.get(
            '/folder', parameters={'name': dataMap[0]['name'],
                               'parentId': catalog['_id'],
                               'parentType': 'folder'}
        )
        try:
            resource = folders[0]
        except IndexError:
            items = self.girder_client.get(
                '/item', parameters={'folderId': catalog['_id'],
                                     'name': dataMap[0]['name']})
            try:
                resource = items[0]
            except IndexError:
                errormsg = 'Registration failed. Aborting!'
                raise ValueError(errormsg)

        # Try to come up with a good name for the dataset
        long_name = resource['name']
        long_name = long_name.replace('-', ' ').replace('_', ' ')
        shortened_name = textwrap.shorten(text=long_name, width=30)

        user = self.girder_client.get('/user/me')
        payload = {
            'authors': user['firstName'] + ' ' + user['lastName'],
            'title': 'A Tale for \"{}\"'.format(shortened_name),
            'dataSet': [
                {
                    'mountPath': '/' + resource['name'],
                    'itemId': resource['_id'],
                    '_modelType': resource['_modelType']
                }
            ],
            'public': False,
            'published': False
        }

        # allow to override title, etc. MUST contain imageId
        payload.update(tale_kwargs)
        tale = self.girder_client.post('/tale', json=payload)

        if spawn:
            self.job_manager.updateProgress(
                message='Creating a Tale container', total=total, current=3)
            try:
                instance = self.girder_client.post(
                    '/instance', parameters={'taleId': tale['_id']})
            except girder_client.HttpError as resp:
                try:
                    message = json.loads(resp.responseText).get('message', '')
                except json.JSONDecodeError:
                    message = str(resp)
                errormsg = 'Unable to create instance. Server returned {}: {}'
                errormsg = errormsg.format(resp.status, message)
                raise ValueError(errormsg)

            while instance['status'] == InstanceStatus.LAUNCHING:
                # TODO: Timeout? Raise error?
                time.sleep(1)
                instance = self.girder_client.get(
                    '/instance/{_id}'.format(**instance))
        else:
            instance = None

        self.job_manager.updateProgress(
            message='Tale is ready!', total=total, current=total)
        # TODO: maybe filter results?
        return {'tale': tale, 'instance': instance}
