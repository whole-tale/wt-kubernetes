#!/usr/bin/python

import sys
import json
import base64

def read_domain_certs(acme_json_path, domain):
    with open(acme_json_path) as acme_json_file:
        acme_json = json.load(acme_json_file)

    certs_json = acme_json['Certificates']
    domain_certs = [cert for cert in certs_json
                    if cert['Domain']['Main'] == domain]

    if not domain_certs:
        raise RuntimeError(
            'Unable to find certificate for domain "%s"' % (domain,))
    elif len(domain_certs) > 1:
        raise RuntimeError(
            'More than one (%d) certificates for domain "%s"' % (domain,))

    [domain_cert] = domain_certs
    return (base64.b64decode(domain_cert['Key']),
            base64.b64decode(domain_cert['Certificate']))


acmejson = sys.argv[1]

(pk, cr) = read_domain_certs(acmejson, "*.local.wholetale.org")

crtFile = sys.argv[2]
keyFile = sys.argv[3]

with open(crtFile, "w") as f:
	f.write(cr)

with open(keyFile, "w") as f:
	f.write(pk)