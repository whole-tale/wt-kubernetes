#!/bin/bash

docker build -t hategan/wt-webdav-plugin . &&\
docker push hategan/wt-webdav-plugin:latest
