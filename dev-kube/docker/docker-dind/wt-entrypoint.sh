#!/bin/sh

mkdir -p /etc/docker/certs.d/registry:443

cp /etc/docker/certs.d/registry/ca.crt /etc/docker/certs.d/registry:443

exec dockerd-entrypoint.sh
