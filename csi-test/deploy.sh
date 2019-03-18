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
run "Checking settings" mustBeSet CREATE_CLUSTER CLUSTER_NAME

if [ "$CREATE_CLUSTER" == "1" ]; then
	if [ "$CLUSTER_TYPE" == "gke" ]; then
		run "Checking GKE settings" mustBeSet GKE_USER_ACCOUNT
		runif "$GKE_PROJECT_ID" "Setting GKE project" gcloud config \
			set project "$GKE_PROJECT_ID"
		runif "$GKE_COMPUTE_REGION" "Setting GKE region" gcloud config \
			set compute/region "$GKE_COMPUTE_REGION"

		# Need 3 nodes for this example: girder, mongo, and tales
		if ! contains "$CLUSTER_NAME" gcloud container clusters list || [ "$CONTINUE" == "0" ] ; then
			run "Creating GKE cluster" gcloud container clusters create \
				"$CLUSTER_NAME" --num-nodes=1 --machine-type=n1-standard-2
			run "Generating kubeconfig entry" gcloud container clusters \
				get-credentials "$CLUSTER_NAME"
			run "Enabling RBAC" kubectl create clusterrolebinding cluster-admin-binding \
				--clusterrole cluster-admin --user "$GKE_USER_ACCOUNT"
		fi
	elif [ "$CLUSTER_TYPE" == "minikube" ]; then
		if ! minikube status 2>&1 >>/dev/null || [ "$CONTINUE" == "0" ] ; then
			# Just in case minikube wants root, do this and hope that sudo is configured
			# to not always ask for the password
			echo -n "Starting minikube cluster"
			sudo true
			run "Creating minikube cluster" minikube start --vm-driver="$MINIKUBE_VM_TYPE" \
				--mount-string="$MY_ABS_DIR/volume-dirs:/volume-dirs" --mount \
				--extra-config=apiserver.authorization-mode=RBAC \
				--feature-gates=MountPropagation=true
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
fi

run "Deploying WebDAV plugin" kubectl create -f ./csi-drivers/deployment
run "Waiting a bit" sleep 5

run "Deploying app" kubectl create -f ./test
