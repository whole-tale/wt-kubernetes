# WholeTale on Kubernetes

This repository deploys WholeTale on Kubernetes. At this time, only GKE is supported.

## Quick start

Follow the following steps to create a deployment:

1. If desired, edit `settings` to customize the deployment. The provided settings should produce a working deployment, so there is no need to edit this file for a sample deployment.
2. Create a secrets file from the provided sample:
    ```
    cp secrets.example secrets
    ```
3. Edit the `secrets` file and fill in the relevant values (currently Globus app credentials).
4. Obtain `acme.json` (ask on Slack) and copy it into the `certs` directory.
5. Run
    ```
    ./deploy.sh -k
    ```
6. Wait (the cluster creation takes a few minutes, and the ingress creation also takes a few minutes)

## Usage

The relevant scripts are `deploy.sh` and `clean.sh`. You can run them with the `-h` flag for details about options. The most relevant option to both is `-k` which is used to specify that a GKE cluster should be created/deleted. Without `-k`, `deploy.sh` will create the necessary Kubernetes objects on an existing cluster (created previously by `deploy.sh -k`), whereas `clean.sh` will delete the objects created by `deploy.sh` without deleting the cluster.

## Inner workings

Running on Kubernetes requires a modified version of `gwvolman`. This is available in the `dev-kube-2.0` branch. It essentially implements two versions
of `gwvolman`: a docker based version and a kubernetes version, selectable using the `DEPLOYMENT_TYPE` environment variable, for which two possible values are recognized (`docker` and `kubernetes`).

The Kubernetes variant uses a docker-in-docker image to build the docker images needed by tales. The tales run in Kubernetes pods. The tale filesystem is built by a Kubernetes init container that runs in the tale pod. For the deployment specification, a (pystache) template file is used, which can be found in `gwvolman/gwvolman/templates`.

## Custom images

A number of custom images are needed to work around various problems. These can be found in the `docker` subdirectory. Each subdirectory has a `settings` file which should at least be updated with the destination image tag. What follows is a brief description of why each custom image is needed.

1. Kubernetes sets a number of environment variables with information about the current pod or service. In particular, because the girder service is called `girder`, it sets `GIRDER_PORT`. And it sets it to something like `tcp://<ip>...`. This causes girder to fail because it expects `GIRDER_PORT` to contain an integer port number to which the girder server should be bound. A special entry point is needed to unsed this environment variable.

2. The registry is used with a local DNS name (i.e., `registry`). This confuses docker, since it cannot really distinguish syntactically between a username and a local DNS name, so it opts for a username in this case. That is, unless an explicit port is specified (e.g., `registry:443`). In order to use a registry with Kubernetes, it should be a TLS secured registry. Since we use a self-signed certificate for the registry, the certificate needs to be deployed on the docker-in-docker container at `/etc/docker/certs.d/registry:443/`. This would be a straightfoward thing of mounting a file from a Kubernetes secret at the relevant path, except colons are not accepted in `volumeMounts[].pathName`. So a custom docker-in-docker image is needed with an entrypoint that copies the certificate to the proper directory.

3. Besides the custom gwvolman code that works with Kubernetes, the gwvolman image needs a proper `init` process. The reason is the implementation of the webdav filesystem. Behind the scenes, it uses FUSE. The unmount call for davfs2 essentially kills the FUSE process and waits for it to disappear form the process list. In a vanilla docker container, this never happens, since there is no init process to reap the dead FUSE process. The consequence is that ummount calls on a webdav mount hang indefinitely. This can cause all kinds of havoc in Kubernetes. The solution is to have an init process inside the container that does the mounting/ummounting.

## Random notes

* The default memory allocated to containers (even on a fattier node) may not be sufficient for building nontrivial images with docker-in-docker. The current code requests 7GB of memory for the dind container (see `deployment-worker.taml`).
