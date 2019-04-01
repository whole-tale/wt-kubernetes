#!/bin/bash

wait_for_file() {
	FILE=$1
	DIR=`readlink -m $FILE`
	while [ ! -f $FILE ]; do
		echo "Missing $FILE. Copy it into $DIR and press any key..."
		read -s -n 1
	done
}

extract_file() {
	ARCHIVE=$1
	FILE=$2
	
	tar --strip-components=1 -C certs -xf $ARCHIVE $FILE
	EXTRACTION_OK=$?
	if [ "$EXTRACTION_OK" != "0" ] ; then
		echo "The archive $ARCHIVE is missing the file $FILE. Ensure that you have the correct .tar file and press any key..."
		read -s -n 1
		return 1
	else
		echo "$FILE extracted successfully"
		return 0
	fi
}

run() {
	"$@"
	if [ "$?" != "0" ]; then
		echo "$@ failed"
		exit 1
	fi
}

CERTS_OK=0

while [ "$CERTS_OK" == "0" ] ; do
	echo "Checking certificates"
	wait_for_file certs/certs.tar
	echo "Certificates archive found"

	extract_file certs/certs.tar certs/dev.key && \
	extract_file certs/certs.tar certs/dev.crt && \
	extract_file certs/certs.tar acme/acme.json
	
	CERTS_OK=!$?
done

chmod 600 certs/acme.json
./extract_acme_cert.py certs/acme.json certs/ssl.crt certs/ssl.key
chmod 600 certs/ssl.key