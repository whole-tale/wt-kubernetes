#!/bin/bash

source ../../settings

docker build -t $IMAGE_NAMESPACE/wsgidav-server-test . &&\
docker push $IMAGE_NAMESPACE/wsgidav-server-test:latest
