#!/bin/sh
set -eu

# shellcheck source=/dev/null
. /etc/os-release
if [ "$ID" != debian ] || [ "${VERSION_CODENAME:-}" != bookworm ]; then
    echo >&2 'docker-in-docker requires Debian Bookworm; use slim-bookworm.'
    exit 1
fi
case "$(dpkg --print-architecture)" in
    amd64 | arm64) ;;
    *)
        echo >&2 'docker-in-docker supports amd64 and arm64 only.'
        exit 1
        ;;
esac

apt-get update
apt-get install -y --no-install-recommends \
    bash ca-certificates curl iptables tini util-linux
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/debian/gpg \
    -o /etc/apt/keyrings/docker.asc
chmod 0644 /etc/apt/keyrings/docker.asc
cat >/etc/apt/sources.list.d/docker.sources <<SOURCES
Types: deb
URIs: https://download.docker.com/linux/debian
Suites: bookworm
Components: stable
Architectures: $(dpkg --print-architecture)
Signed-By: /etc/apt/keyrings/docker.asc
SOURCES
apt-get update
apt-get install -y --no-install-recommends \
    "docker-ce${DIND_DOCKER_VERSION:+=$DIND_DOCKER_VERSION}" \
    "docker-ce-cli${DIND_DOCKER_VERSION:+=$DIND_DOCKER_VERSION}" \
    containerd.io docker-buildx-plugin docker-compose-plugin
usermod -aG docker py
rm -rf /var/lib/apt/lists/*
