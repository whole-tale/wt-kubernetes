#!/bin/bash

source ./settings

docker build --build-arg "GWVOLMAN_BRANCH=${GWVOLMAN_BRANCH}" -t $TAG . &&\
docker push $TAG
