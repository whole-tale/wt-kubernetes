FROM ubuntu:xenial

RUN apt-get update -qqy && \
  apt-get install -qy software-properties-common python3-software-properties && \
  DEBIAN_FRONTEND=noninteractive apt-get -qy install \
    build-essential \
    vim \
    git \
    wget \
    python3 \
    fuse \
    davfs2 \
    libffi-dev \
    libssl-dev \
    libjpeg-dev \
    zlib1g-dev \
    libfuse-dev \
    inetutils-ping \
    telnet \
    libpython3-dev && \
  apt-get -qqy clean all && \
  echo "user_allow_other" >> /etc/fuse.conf && \
  rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

RUN wget https://bootstrap.pypa.io/get-pip.py && python3 get-pip.py

RUN pip install --no-cache-dir celery==4.2.1 fusepy==3.0.1 girder-client==2.4.0 \
  girder-worker==0.5.0 redis==2.10.6 pycurl requests pyyaml kubernetes==9.0.0 \
  kombu==4.2.2post1 pyOpenSSL==18.0.0 jwt==0.5.4 dataone.common==3.2.0 \
  dataone.libclient==3.2.0 dataone.cli==3.2.0

# Needed for reaping daemons (such as FUSE processes)
ENV TINI_VERSION v0.18.0
ADD https://github.com/krallin/tini/releases/download/${TINI_VERSION}/tini /tini
ADD https://github.com/krallin/tini/releases/download/${TINI_VERSION}/tini.asc /tini.asc
RUN gpg --batch --keyserver hkp://p80.pool.sks-keyservers.net:80 --recv-keys 595E85A6B1B4779EA4DAAEC70B588DFF0527A9B7 \
 && gpg --batch --verify /tini.asc /tini
RUN chmod +x /tini 

WORKDIR /gwvolman
ARG GWVOLMAN_BRANCH=dev-kube-2.0
RUN git clone -b $GWVOLMAN_BRANCH https://github.com/whole-tale/gwvolman.git /gwvolman
#COPY gwvolman/requirements.txt /gwvolman/requirements.txt
#COPY gwvolman/setup.py /gwvolman/setup.py
#COPY gwvolman/gwvolman /gwvolman/gwvolman


RUN LDFLAGS="-Wl,-rpath='/usr/local/lib',--enable-new-dtags $LDFLAGS" pip install --no-cache-dir -r requirements.txt -e . && rm -rf /tmp/*

#COPY gwvolman/mount.c /tmp/mount.c
#RUN gcc -Wall -fPIC -shared -o /usr/local/lib/container_mount.so /tmp/mount.c -ldl -D_FILE_OFFSET_BITS=64 && \
#   rm  /tmp/mount.c && \
#   chmod +x /usr/local/lib/container_mount.so && \
#   echo "/usr/local/lib/container_mount.so" > /etc/ld.so.preload

RUN useradd -g 100 -G 100 -u 1000 -s /bin/bash wtuser

RUN girder-worker-config set celery backend redis://redis/ && \
  girder-worker-config set celery broker redis://redis/ && \
  girder-worker-config set girder_worker tmp_root /tmp

ENV C_FORCE_ROOT=1
ENV LC_ALL=C.UTF-8
ENV LANG=C.UTF-8

# Temporary fix for kombu
RUN sed \
  -e 's/return decode(data/&.decode("utf-8")/' \
  -i /usr/local/lib/python3.5/dist-packages/kombu/serialization.py

# https://github.com/whole-tale/gwvolman/issues/51
# https://github.com/whole-tale/wt_home_dirs/issues/18
RUN echo "use_locks 0" >> /etc/davfs2/davfs2.conf && \
  echo "backup_dir .lost+found" >> /etc/davfs2/davfs2.conf && \
  echo "gui_optimize 1" >> /etc/davfs2/davfs2.conf && \
  echo "debug 1" >> /etc/davfs2/davfs2.conf

COPY runworker /usr/local/bin
COPY talefs /usr/local/bin
COPY init-tale-pod /usr/local/bin
COPY update-node /usr/local/bin

ENTRYPOINT ["/usr/local/bin/runworker"]
