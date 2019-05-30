#!/bin/bash

source ./settings

docker build -t $TAG . &&\
docker push $TAG
