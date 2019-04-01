#!/usr/bin/python
import json
import requests
import time
import os

params = {
    'login': 'admin',
    'email': 'root@dev.null',
    'firstName': 'John',
    'lastName': 'Doe',
    'password': 'arglebargle123',
    'admin': True
}
headers = {
    'Content-Type': 'application/json',
    'Accept': 'application/json'
}

api_url = 'https://girder.local.wholetale.org/api/v1'

# Give girder time to start
connErrCount = 0
while True:
    print('Waiting for Girder to start')
    try:
        r = requests.get(api_url)
        if r.status_code == 200:
            break
    except requests.exceptions.ConnectionError:
        connErrCount = connErrCount + 1
        if connErrCount > 10:
            raise Exception('Could not connect to Girder')
    time.sleep(2)

print('Creating admin user')
r = requests.post(api_url + '/user', params=params, headers=headers)
print('Response text: %s' % r.text)
r.raise_for_status()

# Store token for future requests
headers['Girder-Token'] = r.json()['authToken']['token']

print('Creating default assetstore')
r = requests.post(api_url + '/assetstore', headers=headers,
                  params={'type': 1, 'name': 'GridFS', 'db': 'gridfs',
                          'shard': False, 'replicaset': None})

print('Enabling plugins')
plugins = ['oauth', 'gravatar', 'jobs', 'worker', 'wt_data_manager',
           'wholetale', 'wt_home_dir']
r = requests.put(
    api_url + '/system/plugins', headers=headers,
    params={'plugins': json.dumps(plugins)})
r.raise_for_status()

print('Restarting girder to load plugins')
r = requests.put(api_url + '/system/restart', headers=headers)
r.raise_for_status()

# Give girder time to restart
while True:
    print('Waiting for Girder to restart')
    r = requests.get(api_url + '/oauth/provider', headers=headers,
                     params={'redirect': 'http://blah.com'})
    if r.status_code == 200:
        break
    time.sleep(2)

print('Setting up Plugin')

def getAndCheckEnv(name):
    val = os.environ.get(name)
    if val == "" or val == None:
        raise Exception(name + " is not set")
    return val

settings = [
    {
        'key': 'core.cors.allow_origin',
        'value': 'http://dashboard.local.wholetale.org,https://dashboard.local.wholetale.org,http://localhost:4200'
    }, {
        'key': 'core.cors.allow_headers',
        'value': (
            'Accept-Encoding, Authorization, Content-Disposition, Set-Cookie, '
            'Content-Type, Cookie, Girder-Authorization, Girder-Token, '
            'X-Requested-With, X-Forwarded-Server, X-Forwarded-For, '
            'X-Forwarded-Host, Remote-Addr, Cache-Control'
        )
    }, {
        'key': 'worker.api_url',
        'value': 'http://girder:8080/api/v1'
    }, {
        'key': 'worker.broker',
        'value': 'redis://redis/'
    }, {
        'key': 'worker.backend',
        'value': 'redis://redis/'
    }, {
        'key': 'oauth.globus_client_id',
        'value': getAndCheckEnv('GLOBUS_CLIENT_ID')
    }, {
        'key': 'oauth.globus_client_secret',
        'value': getAndCheckEnv('GLOBUS_CLIENT_SECRET')
    }, {
        'key': 'oauth.providers_enabled',
        'value': ['globus']
    }, {
        'key': 'dm.globus_gc_dir',
        'value': '/opt/globusconnectpersonal'
    }
]

r = requests.put(api_url + '/system/setting', headers=headers,
                 params={'list': json.dumps(settings)})
r.raise_for_status()

print('Create a single recipe')
r_params = {
    'commitId': 'b5d691103d0b9e84a94c6611a6439bf6a82ad528',
    'description': 'Jupyter with iframe support (env)',
    'name': 'whole-tale/jupyter-yt',
    'public': True,
    'url': 'https://github.com/whole-tale/jupyter-yt'
}
r = requests.post(api_url + '/recipe', headers=headers,
                  params=r_params)
r.raise_for_status()
recipe = r.json()

print('Create a single image')
i_params = {
    'config': json.dumps({
        'command': (
            'jupyter notebook --no-browser --port {port} --ip=0.0.0.0 '
            '--NotebookApp.token={token} --NotebookApp.base_url=/{base_path} '
            '--NotebookApp.port_retries=0'
        ),
        'environment': ['CSP_HOSTS=dashboard.local.wholetale.org'],
        'memLimit': '2048m',
        'port': 8888,
        'targetMount': '/home/jovyan/work',
        'urlPath': '?token={token}',
        'user': 'jovyan'
    }),
    'fullName': 'xarthisius/jupyter',
    'icon': (
        'https://raw.githubusercontent.com/whole-tale/jupyter-base/master/'
        'squarelogo-greytext-orangebody-greymoons.png'
    ),
    'iframe': True,
    'name': 'Jupyter Notebook',
    'public': True,
    'recipeId': recipe['_id'],
}
r = requests.post(api_url + '/image', headers=headers,
                  params=i_params)
r.raise_for_status()
image = r.json()

print('Starting image build (this will take a while)...')
r = requests.put(api_url + '/image/{_id}/build'.format(**image),
                 headers=headers)
r.raise_for_status()

print('-------------- You should be all set!! -------------')
print('try going to http://girder.local.wholetale.org:8080 and log in with: ')
print('  user : %s' % params['login'])
print('  pass : %s' % params['password'])
