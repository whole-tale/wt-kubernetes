#!/bin/bash

check_file() {
	FILE=$1
	DIR=`readlink -m $FILE`
	while [ ! -f $FILE ]; do
		echo "Missing $FILE"
		exit 1
	done
}

CERTS_OK=0

echo "Checking certificate"
check_file certs/acme.json
echo "Main certificate file found"

echo "Generating registry cert"
openssl req -x509 -sha256 -nodes -days 365 -newkey rsa:2048 -keyout certs/registry.key -out certs/registry.crt \
  -subj "/C=US/ST=IL/L=Chicago/O=Whole Tale/OU=CI/CN=registry"

chmod 600 certs/acme.json
./extract_acme_cert.py certs/acme.json certs/ssl.crt certs/ssl.key
chmod 600 certs/ssl.key