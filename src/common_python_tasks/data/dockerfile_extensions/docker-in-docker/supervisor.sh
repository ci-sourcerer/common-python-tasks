#!/bin/bash
set -euo pipefail

_prepare_host() {
    if [[ $(id -u) != 0 ]]; then
        echo >&2 'docker-in-docker must start as root with --privileged.'
        return 1
    fi
    if [[ ! -w /sys/fs/cgroup ]]; then
        echo >&2 'docker-in-docker needs writable cgroups; use --privileged.'
        return 1
    fi
    if [[ -d /sys/kernel/security ]] &&
        ! mountpoint -q /sys/kernel/security; then
        mount -t securityfs none /sys/kernel/security
    fi
    _prepare_cgroups
    if ! iptables -nL >/dev/null 2>&1 &&
        iptables-legacy -nL >/dev/null 2>&1; then
        update-alternatives --set iptables /usr/sbin/iptables-legacy
        update-alternatives --set ip6tables /usr/sbin/ip6tables-legacy
    fi
    # Only remove our daemon's PID file, never unrelated processes' files.
    rm -f /var/run/docker.pid
}

_prepare_cgroups() {
    [[ -f /sys/fs/cgroup/cgroup.controllers ]] || return 0
    mkdir -p /sys/fs/cgroup/cpt-init
    local attempt pid controllers
    for ((attempt = 0; attempt < 5; attempt++)); do
        while read -r pid; do
            # Processes can disappear or become immovable while we move them.
            printf '%s\n' "$pid" | tee \
                /sys/fs/cgroup/cpt-init/cgroup.procs >/dev/null 2>&1 || true
        done </sys/fs/cgroup/cgroup.procs
        controllers=$(sed 's/[^ ]\+/+&/g' \
            /sys/fs/cgroup/cgroup.controllers)
        if printf '%s\n' "$controllers" | tee \
            /sys/fs/cgroup/cgroup.subtree_control >/dev/null 2>&1; then
            return 0
        fi
        sleep 0.1
    done
    echo >&2 'docker-in-docker could not enable nested cgroups.'
    return 1
}

_stop_group() {
    local pid=$1
    [[ -n "$pid" ]] || return 0
    kill -TERM -- "-$pid" 2>/dev/null || true
    local attempt
    for ((attempt = 0; attempt < 50; attempt++)); do
        kill -0 -- "-$pid" 2>/dev/null || break
        sleep 0.1
    done
    kill -KILL -- "-$pid" 2>/dev/null || true
    wait "$pid" 2>/dev/null || true
}

_shutdown() {
    trap '' TERM INT
    _stop_group "$app_pid"
    _stop_group "$daemon_pid"
}

_wait_for_docker() {
    local deadline=$((SECONDS + DIND_STARTUP_TIMEOUT))
    while ((SECONDS < deadline)); do
        if ! kill -0 "$daemon_pid" 2>/dev/null; then
            echo >&2 'docker-in-docker daemon exited during startup.'
            return 1
        fi
        if timeout 1 docker --host "$DOCKER_HOST" info >/dev/null 2>&1; then
            return 0
        fi
        sleep 0.2
    done
    echo >&2 'docker-in-docker timed out waiting for the daemon.'
    return 1
}

_main() {
    if [[ ! ${DIND_STARTUP_TIMEOUT:-60} =~ ^[1-9][0-9]{0,3}$ ]]; then
        echo >&2 'DIND_STARTUP_TIMEOUT must be an integer from 1 to 9999.'
        return 1
    fi
    export DIND_STARTUP_TIMEOUT=${DIND_STARTUP_TIMEOUT:-60}
    export DOCKER_HOST=unix:///var/run/docker.sock
    export container=docker
    unset DOCKER_CONTEXT DOCKER_TLS_VERIFY DOCKER_CERT_PATH
    _prepare_host
    daemon_pid=''
    app_pid=''
    trap _shutdown EXIT
    trap 'exit 143' TERM
    trap 'exit 130' INT
    # Keep daemon logs on stderr and expose only the local Unix socket.
    setsid dockerd --host "$DOCKER_HOST" --group docker >&2 &
    daemon_pid=$!
    _wait_for_docker
    setsid setpriv --reuid py --regid py --init-groups \
        env HOME="$(getent passwd py | cut -d: -f6)" USER=py LOGNAME=py \
        /pkg/application-entrypoint.sh "$@" &
    app_pid=$!
    local finished status=0
    wait -n -p finished "$daemon_pid" "$app_pid" || status=$?
    if [[ "$finished" == "$daemon_pid" ]]; then
        echo >&2 'docker-in-docker daemon exited while the app was running.'
        return 1
    fi
    return "$status"
}

_main "$@"
