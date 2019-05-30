#!/bin/bash

source ./settings
source ./lib

DELETE_CLUSTER=0

while getopts ":hk" OPT; do
	case ${OPT} in
		k )
			DELETE_CLUSTER=1
			;;
		h )
			echo "Usage:"
			echo "    deploy.sh [-h] [-k]"
			echo "    -h    display this help message"
			echo "    -k    also delete cluster"
			exit 0
	esac
done


run "Checking settings" mustBeSet CLUSTER_TYPE, CLUSTER_NAME

# clean up files
run "Cleaning up config files" rm -f ./.deploy*.yaml

run "Deleting WT services and deployments" kubectl delete deployment,service,ingress -l app=WholeTale
run "Deleting WT volumes" kubectl delete persistentvolume,persistentvolumeclaim,secret,configmap -l app=WholeTale
run "Deleting WT roles and accounts" kubectl delete serviceaccount,clusterrole,clusterrolebinding,role,rolebinding -l app=WholeTale

if [ "$AUTO_VOLUME_TYPE" == "local" ] && [ "$CLUSTER_TYPE" == "minikube" ]; then
	run "Deleting volume-dirs" sudo rm -rf volume-dirs/*
fi

if [ "$DELETE_CLUSTER" == "1" ]; then
	if [ "$CLUSTER_TYPE" == "gke" ]; then
		emit "Deleting GKE cluster... "
		runif "$GKE_PROJECT_ID" "Setting GKE project" gcloud config set project "$GKE_PROJECT_ID"
		runif "$GKE_COMPUTE_REGION" "Setting GKE region" gcloud config set compute/region "$GKE_COMPUTE_REGION"

		# might want to add some confirmation if using this for anything else than testing
		run "Deleting cluster" gcloud --quiet container clusters delete "$CLUSTER_NAME"
		emitn "done" $C_BRT_GREEN
	elif [ "$CLUSTER_TYPE" == "minikube" ]; then
		run "Stopping minikube" minikube stop
		run "Deleting cluster" minikube delete
	fi
fi
