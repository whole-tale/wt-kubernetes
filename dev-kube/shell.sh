#!/bin/bash

NAME="$1"

ID=`kubectl get pods|grep $NAME|awk '{print $1}'`

kubectl exec -it $ID -- /bin/bash