# Docker-in-Docker currently supports Debian Bookworm on amd64 and arm64.
USER root

# Optional exact APT version, including the epoch and distribution suffix.
ARG DIND_DOCKER_VERSION

COPY --from=cpt-extension-docker-in-docker --chmod=0755 install.sh \
    /usr/local/share/cpt-dind-install.sh
RUN /usr/local/share/cpt-dind-install.sh \
    && rm /usr/local/share/cpt-dind-install.sh

COPY --from=cpt-extension-docker-in-docker --chmod=0755 supervisor.sh \
    /usr/local/bin/cpt-dind-supervisor

RUN mv /pkg/entrypoint.sh /pkg/application-entrypoint.sh \
    && printf '%s\n' '#!/bin/sh' \
        'exec /usr/bin/tini -- /usr/local/bin/cpt-dind-supervisor "$@"' \
        >/pkg/entrypoint.sh \
    && chmod 0755 /pkg/entrypoint.sh

ENV DOCKER_HOST=unix:///var/run/docker.sock
VOLUME ["/var/lib/docker", "/var/lib/containerd"]

# The generic final and debug stages inherit this startup-user selection.
# The wrapper drops to py only for the application, after Docker is ready.
ARG RUNTIME_USER=root
USER ${RUNTIME_USER}
