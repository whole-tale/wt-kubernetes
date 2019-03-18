FROM centos:7.6.1810

# Copy plugin from build _output directory
COPY bin/wtwebdavplugin /wtwebdavplugin

RUN yum -y install epel-release && yum -y install jq && yum clean all

ENTRYPOINT ["/wtwebdavplugin"]
