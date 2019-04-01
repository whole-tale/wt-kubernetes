#!/bin/bash

setBranches() {
    pushd /girder

    while [ "$1" != "" ]; do
        REPO=$1
        PLUGIN=$2
        BRANCH=$3
        shift 3
        cd /girder/plugins
        if [ -d $PLUGIN ]; then
            rm -rf $PLUGIN
        fi
        git clone $REPO $PLUGIN
        cd $PLUGIN
        git checkout $BRANCH
        cd /girder
    done

    popd
}

if [ "$HOST_UID" == "" ]; then
    echo "Missing HOST_UID!"
    #sleep 120
else
    usermod -u $HOST_UID girder
    groupmod -g $HOST_GID girder
fi

# add a password and enable login because the gridftp server 
# refuses to start if the user account is disabled; it also
# refuses to start with a message about the login being disabled
# even if passwd -S shows a proper 'P' if the user has the default
# system shell, which corresponds to a blank shell in /etc/passwd, 
# because gridfpt has its own standards
# (see globus_i_gfs_data.c: globus_l_gfs_validate_pwent() and man 5 passwd)
STATUS=`passwd -S girder | awk '{print $2}'`
if [ "$STATUS" == "L" ]; then
    usermod -p `openssl rand -base64 32` girder
    usermod -U girder
fi
usermod -s /bin/bash girder

setBranches $DEPLOY_DEV_BRANCHES

sudo -u girder "$@"

EC=$?

echo "Girder exit code: $EC"

if [ "$EC" != "0" ]; then
	echo "Girder failed. Waiting..."
fi

sleep 3600