#!/bin/bash

#
# See https://github.com/kubernetes/kubernetes/issues/60099
#
# Kubernetes sets <SERVICENAME>_PORT to some URL nonsense
# and the girder config infrastructure looks at this env var
# to override the port value in the config files. Needless 
# to say, it tries to parse an URL as an int, which fails.
#
# Hey, Kubernetes, when you want to define environment 
# variables like this, prefix them with something specific
# to your infrastructure so that they don't clash with 
# existing variables.

unset GIRDER_PORT

exec /usr/local/bin/docker-entrypoint.sh "$@"
