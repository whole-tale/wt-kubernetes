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
run "Checking settings" mustBeSet CREATE_CLUSTER CLUSTER_NAME DOMAIN_NAME GLOBUS_CLIENT_ID GLOBUS_CLIENT_SECRET VOLSZ_WORKSPACE
export DOMAIN_NAME
run "Unpacking certificate" ./check_certs.sh

if [ "$CREATE_CLUSTER" == "1" ]; then
	if [ "$CLUSTER_TYPE" == "gke" ]; then
		run "Checking GKE config" mustBeSet GKE_INITIAL_NODE_COUNT GKE_MACHINE_TYPE
		emit "Creating GKE cluster... "
		runif "$GKE_PROJECT_ID" "Setting GKE project" gcloud config \
			set project "$GKE_PROJECT_ID"
		runif "$GKE_COMPUTE_REGION" "Setting GKE region" gcloud config \
			set compute/region "$GKE_COMPUTE_REGION"
		
		if ! contains "$CLUSTER_NAME" gcloud container clusters list || [ "$CONTINUE" == "0" ] ; then
			# The repo2docker builds are memory hungry
			run "Creating GKE cluster" gcloud container clusters create \
				"$CLUSTER_NAME" --num-nodes=$GKE_INITIAL_NODE_COUNT --machine-type=$GKE_MACHINE_TYPE
			run "Generating kubeconfig entry" gcloud container clusters \
				get-credentials "$CLUSTER_NAME"
		fi
		#run "Adding admin user " kubectl create clusterrolebinding cluster-admin-binding \
		#	--clusterrole cluster-admin --user $(gcloud config get-value account)
		#run "Enabling NGINX ingress (1)" kubectl apply -f \
		#	https://raw.githubusercontent.com/kubernetes/ingress-nginx/master/deploy/mandatory.yaml
		#run "Enabling NGINX ingress (2)" kubectl apply -f \
		#	https://raw.githubusercontent.com/kubernetes/ingress-nginx/master/deploy/provider/cloud-generic.yaml
		emitn "done" $C_BRT_GREEN
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
	#if [ "$CLUSTER_TYPE" != "none" ]; then
	#	echo -n "Deploying volume plugins"
	#		run "Deploying WebDAV plugin" kubectl create -f ./csi-drivers/deployment
	#		run "Waiting a bit" sleep 5
	#	echo
	#fi
	
fi

createTLSSecret "registry-cert-secret" ./certs/registry.key ./certs/registry.crt
createTLSSecret "site-cert-secret" ./certs/ssl.key ./certs/ssl.crt
createSecretFromFile "registry-secret" secret-registry

# Special kind of secret for docker registries. See 
# https://kubernetes.io/docs/tasks/configure-pod-container/pull-image-private-registry/ 
run "Creating docker-registry secret" kubectl create secret docker-registry registry-credentials \
	--docker-server="registry:443" --docker-username="fido" --docker-password="secretpass" \
	--docker-email="fido@example.com"

run "Creating gwvolman account" kubectl create -f ./serviceaccount-worker.yaml

echo -n "Creating volumes: "
createVolumeClaim mongo $VOLSZ_MONGO_DATA
createVolumeClaim registry-storage $VOLSZ_REGISTRY_STORAGE
createVolumeClaim girder-ps $VOLSZ_GIRDER_PS
createVolumeClaim docker-storage $VOLSZ_DOCKER_STORAGE
createVolumeClaim image-build-dirs $VOLSZ_IMAGE_BUILD_DIRS
echo


echo -n "Deploying: "
export MONGO_IMAGE REDIS_IMAGE REGISTRY_IMAGE GIRDER_IMAGE DASHBOARD_IMAGE WORKER_IMAGE VOLSZ_WORKSPACE
deploy mongo
deploy redis
deploy registry
createConfigmap girder-configmap ./girder/girder.local.cfg ./girder/start ./girder/k8s-entrypoint.sh
deploy girder
deploy dashboard
createConfigmap worker-configmap ./images/gwvolman/kubetest.py
deploy worker

if ! exists ingress ingress || [ "$CONTINUE" == "0" ] ; then
	export DOMAIN_NAME
	createFromYaml "ingress" "ingress"
fi
echo

export GLOBUS_CLIENT_ID
export GLOBUS_CLIENT_SECRET

GIRDER_URL="https://girder.$DOMAIN_NAME"

if [ "$CLUSTER_TYPE" == "gke" ]; then
	./wait_for_ingress.sh "$DOMAIN_NAME" "$GIRDER_URL"
fi

run "Setting up girder" ./setup_girder.sh

if [ "$KEEP_TEMPS" == "0" ]; then
	run "Deleting temporary yaml files" rm -f tmp/.*.yaml
	run "Deleting temporary directory" rmdir tmp
fi
