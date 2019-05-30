#!/bin/bash

LOG=kube.log
DOMAIN_NAME="$1"
GIRDER_URL="$2"

if [ "$DOMAIN_NAME" == "" ]; then
	source ./settings
	GIRDER_URL="https://girder.$DOMAIN_NAME"
fi

echo -n "Waiting for ingress..."
# Wait for IP to show up

INGRESS_IP=

getIngressIp() {
	# It prints the column name on the first line and the IP on the second, hence sed
	INGRESS_IP=`kubectl get ingress -o custom-columns=ADDRESS:status.loadBalancer.ingress[0].ip|sed -n 2p`
}


getIngressIp
while [ "$INGRESS_IP" == "<none>" ] ; do
	echo -n '.'
	sleep 5
	getIngressIp
done

IP_FROM_DOMAIN_NAME=`getent ahostsv4 $DOMAIN_NAME|head -n 1|awk '{print $1}'`

if [ "$INGRESS_IP" != "$IP_FROM_DOMAIN_NAME" ]; then
	echo "IP from domain name ($IP_FROM_DOMAIN_NAME) differs from ingress IP ($INGRESS_IP)"
	exit 5
fi

BG_SRV_COUNT=0
while [ "$BG_SRV_COUNT" == "0" ]; do
	# format is
	#   ingress.kubernetes.io/backends:          {<bs1>:<status1>,<bs2>:<status2>,...}
	BG_SRV_COUNT=`kubectl describe ingress ingress | grep "ingress.kubernetes.io/backends"|grep -o ":"|wc -l`
done

# subtract one for the main ':'
BG_SRV_COUNT=$((BG_SRV_COUNT - 1))
GIRDER_UP=0

setHealthySrvCount() {
	HEALTHY_SRV_COUNT=`kubectl describe ingress ingress | grep "ingress.kubernetes.io/backends"|grep -o "HEALTHY"|wc -l`
}

isGirderUp() {
	curl -k -X GET "$GIRDER_URL/api/v1" 2>/dev/null|grep "Girder - REST API" >/dev/null
	EC=$?
	if [ "$EC" == "0" ]; then
		GIRDER_UP=1
	else
		GIRDER_UP=0
		curl -k -X GET "$GIRDER_URL/api/v1"
	fi
}

setHealthySrvCount
isGirderUp
while [ "$HEALTHY_SRV_COUNT" != "$BG_SRV_COUNT" ] || [ "$GIRDER_UP" == "0" ] ; do
	echo "HSC: $HEALTHY_SRV_COUNT, BSC: $BG_SRV_COUNT, GU: $GIRDER_UP"
	echo -n 'o'
	sleep 5
	setHealthySrvCount
	isGirderUp
done
echo
echo "All up!"