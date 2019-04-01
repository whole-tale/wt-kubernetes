#!/bin/bash

docker build -t hategan/wt-girder-gke . &&\
docker push hategan/wt-girder-gke:latest
