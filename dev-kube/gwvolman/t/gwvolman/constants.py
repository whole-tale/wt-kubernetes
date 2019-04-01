#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import socket

API_VERSION = '2.1'
DEFAULT_USER = 1000
DEFAULT_GROUP = 100
ENABLE_WORKSPACES = True
MOUNTPOINTS = ['data', 'home']
if ENABLE_WORKSPACES:
    MOUNTPOINTS.append('workspace')

try:
    DEFAULT_GIRDER_API_URL = 'http://' + socket.gethostbyname('girder') + ':8080/api/v1'
except socket.gaierror:
    DEFAULT_GIRDER_API_URL = 'https://girder.dev.wholetale.org/api/v1'
GIRDER_API_URL = os.environ.get('GIRDER_API_URL', DEFAULT_GIRDER_API_URL)


class InstanceStatus(object):
    LAUNCHING = 0
    RUNNING = 1
    ERROR = 2


class DataONELocations:
    """
    An enumeration that describes the different DataONE
    endpoints.
    """
    # Production coordinating node
    prod_cn = 'https://cn.dataone.org/cn/v2'
    # Development member node
    dev_mn = 'https://dev.nceas.ucsb.edu/knb/d1/mn/v2'
    # Development coordinating node
    dev_cn = 'https://cn-stage-2.test.dataone.org/cn/v2'


class ExtraFileNames:
    """
    When creating data packages we'll have to create additional files, such as
     the zipped recipe, the tale.yml file, the metadata document, and possibly
      more. Keep their names store here so that they can easily be referenced and
      changed in a single place.
    """
    # Name for the tale config file
    tale_config = 'tale.yml'
    license_filename = 'LICENSE'
    environment_file = 'docker-environment.tar.gz'


"""
A dictionary that maps a license ID to a license file
"""
license_files = {'CC0-1.0': 'cc0.txt',
                 'CC-BY-3.0': 'ccby3.txt',
                 'CC-BY-4.0': 'ccby4.txt'}

"""
A dictionary for the descriptions of the manually added package files.
"""
file_descriptions = {
    ExtraFileNames.environment_file:
        'Holds the dockerfile and additional configurations for the '
        'underlying compute environment. This environment was used as the '
        'base image, and includes the the IDE that is used while running the Tale.',
    ExtraFileNames.tale_config:
        'A configuration file, holding information that is needed to '
        'reproduce the compute environment.',
    ExtraFileNames.license_filename:
        'The package\'s licensing information.'
}

"""
The DataONE packages need to have descriptions in the EML metadata. The
license_text dictionary holds the descriptions for each license type. If
you add a license to support, be sure to add the description below.
"""
license_text = {'CC0-1.0': 'This work is dedicated to the public domain under the Creative '
                           'Commons Universal 1.0 Public Domain Dedication. To view a copy '
                           'of this dedication, visit '
                           'https://creativecommons.org/publicdomain/zero/1.0/.',
                'CC-BY-3.0': 'This work is dedicated to the public domain under the '
                             'Creative Commons '
                             'license CC-BY 3.0. To view a copy of this dedication, '
                             'visit https://creativecommons.org/licenses/by/3.0/us/legalcode.',
                'CC-BY-4.0': 'This information is released to the public domain under the '
                             'Creative Commons license CC-BY 4.0 '
                             '(see: https://creativecommons.org/licenses/by/4.0/). It may be '
                             'distributed, remixed, and built upon. You must give appropriate '
                             'credit, provide a reasonable manner, but not in any way that '
                             'suggests the licensor endorses you or your use. The consumer '
                             'of these data ("Data User" herein) should realize that '
                             'these data may be actively used by others for ongoing '
                             'research and that coordination may be necessary to prevent '
                             'duplicate publication. The Data User is urged to '
                             'contact the authors of these data if any questions '
                             'about methodology or results occur. Where '
                             'appropriate, the Data User is encouraged to consider '
                             'collaboration or co-authorship with the authors. The Data '
                             'User should realize that misinterpretation of data may occur if '
                             'used out of context of the original study. While substantial '
                             'efforts are made to ensure the accuracy of data and '
                             'associated documentation, complete accuracy of data sets '
                             'cannot be guaranteed. All data are made available "as is." '
                             'The Data User should be aware, however, that data '
                             'are updated periodically and it is the responsibility '
                             'of the Data User to check for new versions of the data. '
                             'were obtained shall not be liable for damages '
                             'resulting from any use or misinterpretation '
                             'of the data. Thank you.'}
