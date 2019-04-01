#!/bin/bash

source ./settings
source ./lib

CONTINUE=1
KEEP_TEMPS=0
CREATE_CLUSTER=0

while getopts ":hck" OPT; do
	case ${OPT} in
		c )
			CONTINUE=0
			;;
		t )
			KEEP_TEMPS=1
			;;
		k )
			CREATE_CLUSTER=1
			;;
		h )
			echo "Usage:"
			echo "    deploy.sh [-h] [-c] [-t]"
			echo "    -h    display this help message"
			echo "    -c    do not continue; by default, this tool only"
			echo "          attempts to start individual services if not"
			echo "          already started. If this option is specified,"
			echo "          and some services are already started,"
			echo "          failures may occur."
			echo "    -k    create cluster"
			echo "    -t    do not delete temporary .yaml files created"
			echo "          during deployment."
			exit 0
	esac
done

checkDir
run "Creating temporary directory" mkdir -p tmp
run "Checking settings" mustBeSet CREATE_CLUSTER CLUSTER_NAME DOMAIN_NAME GLOBUS_CLIENT_ID GLOBUS_CLIENT_SECRET
export DOMAIN_NAME
run "Unpacking certificate" ./check_certs.sh

if [ "$CREATE_CLUSTER" == "1" ]; then
	if [ "$CLUSTER_TYPE" == "gke" ]; then
		runif "$GKE_PROJECT_ID" "Setting GKE project" gcloud config \
			set project "$GKE_PROJECT_ID"
		runif "$GKE_COMPUTE_REGION" "Setting GKE region" gcloud config \
			set compute/region "$GKE_COMPUTE_REGION"

		# Need 3 nodes for this example: girder, mongo, and tales
		if ! contains "$CLUSTER_NAME" gcloud container clusters list || [ "$CONTINUE" == "0" ] ; then
			run "Creating GKE cluster" gcloud container clusters create \
				"$CLUSTER_NAME" --num-nodes=3
			run "Generating kubeconfig entry" gcloud container clusters \
				get-credentials "$CLUSTER_NAME"
		fi
	elif [ "$CLUSTER_TYPE" == "minikube" ]; then
		if ! minikube status 2>&1 >>/dev/null || [ "$CONTINUE" == "0" ] ; then
			# Just in case minikube wants root, do this and hope that sudo is configured
			# to not always ask for the password
			echo -n "Starting minikube cluster"
			sudo true
			run "Creating minikube cluster" minikube start --vm-driver="$MINIKUBE_VM_TYPE" \
				--mount-string="$MY_ABS_DIR/volume-dirs:/volume-dirs" --mount \
				--extra-config=apiserver.authorization-mode=RBAC
			# see https://github.com/kubernetes-csi/docs/issues/37
			run "Applying minikube fix" minikube ssh "sudo ln -sfn /run /var/run"

			run "Creating admin role" kubectl create clusterrolebinding add-on-cluster-admin \
				--clusterrole=cluster-admin --serviceaccount=kube-system:default
			run "Enabling ingress controller" minikube addons enable ingress
			echo
		fi
	elif [ "$CLUSTER_TYPE" == "none" ]; then
		echo "Skipping cluster creation (CLUSTER_TYPE is 'none')"
	fi
	if [ "$CLUSTER_TYPE" != "none" ]; then
		echo -n "Deploying volume plugins"
			run "Deploying WebDAV plugin" kubectl create -f ./csi-drivers/deployment
			run "Waiting a bit" sleep 5
		echo
	fi
fi

createTLSSecret "dev-cert-secret" ./certs/dev.key ./certs/dev.crt
createTLSSecret "site-cert-secret" ./certs/ssl.key ./certs/ssl.crt
createSecretFromFile "registry-secret" secret-registry

echo -n "Creating volumes: "
createVolume mongo $VOLSZ_MONGO_DATA
createVolume registry-storage $VOLSZ_REGISTRY_STORAGE
createVolume girder-ps $VOLSZ_GIRDER_PS
echo


echo -n "Deploying: "
createFromYaml "gwvolman-dev volume claim" volume-claim-gwvolman-dev
createFromYaml "gwvolman-dev volume" volume-gwvolman-dev
startService mongo
startService redis
startService registry
startService girder -c ./girder/girder.local.cfg ./girder/start
startService dashboard
startService worker -c ./gwvolman/kubetest.py

if ! exists ingress ingress || [ "$CONTINUE" == "0" ] ; then
	export DOMAIN_NAME
	createFromYaml "ingress" "ingress"
fi
echo


CLUSTER_IP=`kubectl cluster-info|grep "master"|awk '{print $6}'|awk -F ':' '{print substr($2, 3)}'`
echo "Cluster IP: $CLUSTER_IP"
export GLOBUS_CLIENT_ID
export GLOBUS_CLIENT_SECRET
run "Setting up girder" ./setup_girder.py "http://$CLUSTER_IP:$GIRDER_EXTERNAL_PORT"

if [ "$KEEP_TEMPS" == "0" ]; then
	run "Deleting temporary yaml files" rm -f tmp/.*.yaml
	run "Deleting temporary directory" rmdir tmp
fi
