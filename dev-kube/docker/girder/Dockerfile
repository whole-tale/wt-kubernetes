FROM wholetale/girder:latest

RUN apt-get update
RUN apt-get install -y sudo mc

COPY --chown=root:root ./docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh

ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
CMD ["girder", "serve"]