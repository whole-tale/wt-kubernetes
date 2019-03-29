# Almost Working Kubernetes CSI WebDAV Driver Example

This is an attempt at getting a basic custom CSI driver working. The idea here is that integrating a correct CSI driver with the Kubernetes infrastructure is considerably more complex than writing the relevant code that makes up a CSI driver.

## The Basics of CSI Drivers

There are many confusing documents out there with details about how CSI drivers work and how they are supposed to be deployed. There are a few authoritative sources for this, and it is probably best to use these are primary references:

* [The CSI design docs](https://github.com/kubernetes/community/blob/master/contributors/design-proposals/storage/container-storage-interface.md)
* [The official CSI documentation](https://kubernetes-csi.github.io/docs/)
* [The official CSI GitHub repos](https://github.com/kubernetes-csi): this is a collection of relevant code including examples of CSI drivers, deployment specifications, etc.

CSI drivers are executables that communicate using gRPC. They consist of two parts: one that provides information about the driver and the actual driver implementing the attach/detach and mount/unmount functionality. For our purposes, attach/detach is not needed. It is possible and typical to have both parts built into a single executable.

The drivers communicate with officially provided sidecar containers, which act as bridges between the Kubernetes infrastructure and the drivers. This is typically done through UNIX sockets that are created in host directories mounted inside containers. There are two relevant sidecar containers:
* The driver registrar, which queries the driver for information and publishes the resulting information to the Kubernetes infrastructure
* The node plugin, which issues commands to the driver

The registrar, along with an instance of the driver, is typically deployed as a StatefulSet whereas the node plugin (along with respective instances of the driver) is deployed on each pod as a DaemonSet.

### Usage

To test the examples here using the provided containers/drivers/etc, go through the following steps:
* edit the `settings` file
* run `deploy.sh -k`; this does the following:
  * Creates a cluster using the information specified in the settings file. The `minikube` option allows you to run a Kubernetes cluster locally, but has some issues with they way it sets up the host directories (it uses relative symbolic links, which break stuff at some point -- see https://github.com/kubernetes-csi/docs/issues/37). So use `GKE`.
  * Deploys the driver using the deployment specs and access control specs in `csi-drivers/deployment` (a side note here: the access control specs I found on the interwebs, including the ones provided with the official CSI examples above, did not have permissions for watching events, which caused problems)
  * Deploys the test pods which consist of a WebDAV server and a pod that uses the plugin to mount a directory served by the WebDAV server
* to clean up, use `clean.sh -k`

Some notes:
* The `-k` command line option to `deploy.sh` and `clean.sh` instruct the scripts to create/delete the entire cluster. Once `deploy.sh` is run with `-k` and the cluster is created, you can use `deploy.sh` and `clean.sh` without the `-k` option, which will result in the cluster being kept and only the deployments being created/deleted.
* You may want to play with the driver. To do so, create a `go` directory somewhere, then `mkdir -p go/src/github.com`, link `csi-drivers/csi-wt-webdav` in there such that `ls go/src/github.com/csi-wt-webdav/Makefile` works. Then, `export GO_PATH=/path/to/go` where `go` is the directory created in the first step and finally `cd $GO_PATH/src/github.com/csi-wt-webdav && make`
* Some of the images are in my namespace. If you want to use custom images, you may have to change the docker image names in the various `build-and-commit.sh` scripts.

### Status

Things get deployed and the driver and the registrar communicate (i.e., Kubernetes is aware of the driver). However, the mount command times out even when the relevant mount method in the driver consist of printing a message and returning immediately. I suspect that it might not get called at all (I see nothing printed in the logs) or there are some notification issues and some other explanation for the lack of log messages from the driver.

Some troubleshooting steps include checking that the pods are OK (the WebDAV client pod won't work unless it can mount the CSI volume) and looking at logs for the relevant containers (`driver-registrar`, `csi-attacher`, and the driver containers that each of these are connected to)
