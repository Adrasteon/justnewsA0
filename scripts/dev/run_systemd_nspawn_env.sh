#!/usr/bin/env bash
# Lightweight developer helper to create and run a systemd-nspawn container
# for local testing of systemd-based services (e.g. mariadb, redis) without
# using Docker. This is intentionally opt-in and requires a Linux host where
# the developer has permission to run systemd-nspawn (root or via sudo).
#
# NOTE: This script is a convenience helper and aims to be robust but not
# production-grade. It assumes Debian/Ubuntu inside the container and will
# use debootstrap if a container root directory doesn't exist.
#
# Usage:
#   scripts/dev/run_systemd_nspawn_env.sh create   # create filesystem for container
#   scripts/dev/run_systemd_nspawn_env.sh start    # start the container
#   scripts/dev/run_systemd_nspawn_env.sh stop     # stop the container
#   scripts/dev/run_systemd_nspawn_env.sh shell    # run an interactive shell in container
#   scripts/dev/run_systemd_nspawn_env.sh destroy  # destroy the container
#   scripts/dev/run_systemd_nspawn_env.sh status   # show machinectl list

set -euo pipefail

CONTAINER_NAME=${CONTAINER_NAME:-justnews-test}
RESOLVE_MODE=${RESOLVE_MODE:-host} # default to using host resolver so DNS works inside containers
PRIVATE_NETWORK=${PRIVATE_NETWORK:-no} # set to 'yes' to start with a private network namespace
MACHINE_DIR=/var/lib/machines/${CONTAINER_NAME}
DISTRO=${DISTRO:-ubuntu}
SUITE=${SUITE:-24.04}

function require_root() {
    if [[ $(id -u) -ne 0 ]]; then
        echo "This script requires root. Re-run with sudo or as root." >&2
        exit 1
    fi
}

function check_debootstrap() {
    if ! command -v debootstrap >/dev/null 2>&1; then
        echo "debootstrap is required to bootstrap a container filesystem. Install it (apt install debootstrap) and re-run." >&2
        exit 1
    fi
}

function create_container() {
    require_root
    if [[ -d "${MACHINE_DIR}" && -f "${MACHINE_DIR}/etc/os-release" ]]; then
        echo "Container root exists at ${MACHINE_DIR}. Skipping bootstrap.";
        return
    fi

    check_debootstrap

    echo "Bootstrapping ${DISTRO} ${SUITE} into ${MACHINE_DIR} (this may take a few minutes)..."

    # If debootstrap does not contain the requested suite helper, pick a
    # reasonable fallback to improve success on older debootstrap versions.
    if [[ ! -f "/usr/share/debootstrap/scripts/${SUITE}" ]]; then
        echo "debootstrap script for suite '${SUITE}' not found. Falling back to 'jammy' (22.04)"
        SUITE=jammy
    fi
    mkdir -p "${MACHINE_DIR}"
    debootstrap --variant=minbase --arch=$(dpkg --print-architecture) ${SUITE} "${MACHINE_DIR}" http://archive.ubuntu.com/ubuntu

    echo "Basic bootstrap finished. Configuring container for systemd usage..."

    # Make sure systemd runs in container and network utilities available
    # Try installing inetutils-ping, but fall back to iputils-ping if not present
    chroot "${MACHINE_DIR}" /bin/bash -lc "apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y systemd-sysv dbus curl || true"
    chroot "${MACHINE_DIR}" /bin/bash -lc "DEBIAN_FRONTEND=noninteractive apt-get install -y inetutils-ping || apt-get install -y iputils-ping || true"

    # Tune locales/timezone to avoid interactive prompts
    chroot "${MACHINE_DIR}" /bin/bash -lc "DEBIAN_FRONTEND=noninteractive apt-get install -y locales && locale-gen C.UTF-8"

    echo "Bootstrap complete. You can now 'start' the container and install services inside it (mariadb-server, redis-server)."
}

function start_container() {
    require_root
    if [[ ! -d "${MACHINE_DIR}" ]]; then
        echo "Container root ${MACHINE_DIR} doesn't exist. Run 'create' first." >&2
        exit 1
    fi

    echo "Starting ${CONTAINER_NAME} (resolv-conf: ${RESOLVE_MODE}, private-network: ${PRIVATE_NETWORK})..."
    # start container (machinectl or systemd-nspawn)
    # Try to register the machine so it's visible to machinectl. Older
    # versions of systemd-nspawn required an explicit boolean argument.
    # Build systemd-nspawn args. Allow toggling private networking and resolv.conf
    SNAP_ARGS=( -D "${MACHINE_DIR}" --machine=${CONTAINER_NAME} --hostname=${CONTAINER_NAME} --boot --register=yes --resolv-conf=${RESOLVE_MODE} )
    # If using host-resolver mode, copy the host's effective resolver file into
    # the container root so the guest uses real upstream nameservers instead of
    # a loopback stub which won't work inside a private network namespace.
    if [[ "${RESOLVE_MODE}" == "host" ]]; then
        if [[ -f "/run/systemd/resolve/resolv.conf" ]]; then
            echo "Copying host resolver /run/systemd/resolve/resolv.conf -> ${MACHINE_DIR}/etc/resolv.conf"
            mkdir -p "${MACHINE_DIR}/etc"
            # remove dangling symlink if present so we can write the real file
            if [[ -L "${MACHINE_DIR}/etc/resolv.conf" || -f "${MACHINE_DIR}/etc/resolv.conf" ]]; then
                rm -f "${MACHINE_DIR}/etc/resolv.conf" || true
            fi
            cp -f /run/systemd/resolve/resolv.conf "${MACHINE_DIR}/etc/resolv.conf"
        elif [[ -f "/etc/resolv.conf" ]]; then
            echo "Copying host /etc/resolv.conf -> ${MACHINE_DIR}/etc/resolv.conf"
            if [[ -L "${MACHINE_DIR}/etc/resolv.conf" || -f "${MACHINE_DIR}/etc/resolv.conf" ]]; then
                rm -f "${MACHINE_DIR}/etc/resolv.conf" || true
            fi
            cp -f /etc/resolv.conf "${MACHINE_DIR}/etc/resolv.conf"
        fi
    fi
    if [[ "${PRIVATE_NETWORK}" == "yes" ]]; then
        # Use network-veth instead of private-network so the guest receives
        # a veth interface with a routable address (DHCP) for outbound access.
        SNAP_ARGS+=( --network-veth )
    fi
    systemd-nspawn "${SNAP_ARGS[@]}" > /dev/null 2>&1 || true
    # If machinectl knows the machine we prefer to use it to ensure the
    # container is managed correctly.
    machinectl start ${CONTAINER_NAME} || true

    echo "Waiting a few seconds for container to settle..."
    sleep 2
    
        echo "Container started. Use:"
        echo "  sudo machinectl shell ${CONTAINER_NAME} /bin/bash"
        echo "or:"
        echo "  sudo scripts/dev/run_systemd_nspawn_env.sh shell"

        # If the guest was started with network-veth, make sure the host-side
        # veth is configured for forwarding and NAT so the container can reach
        # the internet reliably. This helps when the host's FORWARD policy is
        # DROP (common on workstations with non-default firewall rules).
        if [[ "${PRIVATE_NETWORK}" == "yes" ]]; then
            # Default network the host should assign. If you have a different
            # subnet preference set the HOST_NET/HOST_IP env vars before calling.
            HOST_NET=${HOST_NET:-10.11.12.0/24}
            HOST_IP=${HOST_IP:-10.11.12.1}
            POSTROUTING_SUBNET=${POSTROUTING_SUBNET:-${HOST_NET}}

            # Try to find the host veth which systemd-nspawn creates. It usually
            # has an "altname" like ve-${CONTAINER_NAME} or a name beginning with
            # "ve-${CONTAINER_NAME}"; be generous in the match for cross-systemd
            # compatibility.
            HOST_VETH=$(ip -o link show | grep -E "altname ve-${CONTAINER_NAME}| ve-${CONTAINER_NAME}@|^\d+: ve-${CONTAINER_NAME}" | awk -F': ' '{print $2; exit}' || true)
            if [[ -z "${HOST_VETH}" ]]; then
                # Fall back to any interface that starts with ve-${CONTAINER_NAME}
                HOST_VETH=$(ip -o link show | awk -F': ' '{print $2}' | grep -E "^ve-${CONTAINER_NAME}" | head -n1 || true)
            fi

            if [[ -n "${HOST_VETH}" ]]; then
                echo "Configuring host veth ${HOST_VETH} for container network (${HOST_NET})..."
                ip link set dev "${HOST_VETH}" up || true

                # Add host-side IP if missing
                if ! ip addr show dev "${HOST_VETH}" | grep -q "${HOST_IP}"; then
                    ip addr add "${HOST_IP}/24" dev "${HOST_VETH}" || true
                fi

                # Ensure forwarding and NAT are set up so the container can reach
                # the outside network. Choose a sensible outgoing interface.
                OUT_IF=$(ip route get 8.8.8.8 2>/dev/null | awk '{ for(i=1;i<=NF;i++) if ($i=="dev") {print $(i+1); exit} }')
                if [[ -z "${OUT_IF}" ]]; then
                    OUT_IF=$(ip route | awk '/default/ {print $5; exit}')
                fi

                # Enable forwarding on the host (non-destructive if already set)
                sysctl -w net.ipv4.ip_forward=1 >/dev/null 2>&1 || true

                # Add a safe MASQUERADE rule so the container subnet is NATed
                if [[ -n "${OUT_IF}" ]]; then
                    iptables -t nat -C POSTROUTING -s "${POSTROUTING_SUBNET}" -o "${OUT_IF}" -j MASQUERADE >/dev/null 2>&1 || \
                        iptables -t nat -A POSTROUTING -s "${POSTROUTING_SUBNET}" -o "${OUT_IF}" -j MASQUERADE || true
                fi

                # Allow forwarding for the container subnet (source and destination)
                iptables -C FORWARD -s "${POSTROUTING_SUBNET}" -j ACCEPT >/dev/null 2>&1 || \
                    iptables -A FORWARD -s "${POSTROUTING_SUBNET}" -j ACCEPT || true
                iptables -C FORWARD -d "${POSTROUTING_SUBNET}" -j ACCEPT >/dev/null 2>&1 || \
                    iptables -A FORWARD -d "${POSTROUTING_SUBNET}" -j ACCEPT || true
            else
                echo "Could not detect host veth (ve-${CONTAINER_NAME}) — if DNS/networking continues failing, bring up the host veth and add NAT/FORWARD rules manually."
            fi
        fi

    echo "Container started. Use:"
    echo "  sudo machinectl shell ${CONTAINER_NAME} /bin/bash"
    echo "or:"
    echo "  sudo scripts/dev/run_systemd_nspawn_env.sh shell"
}

function stop_container() {
    require_root
    echo "Stopping ${CONTAINER_NAME} if running..."
    machinectl poweroff ${CONTAINER_NAME} || true
}

function destroy_container() {
    require_root
    echo "Stopping and removing container root ${MACHINE_DIR}"
    machinectl poweroff ${CONTAINER_NAME} || true
    sleep 1
    if [[ -d "${MACHINE_DIR}" ]]; then
        rm -rf "${MACHINE_DIR}"
        echo "Removed ${MACHINE_DIR}"
    else
        echo "No container root found at ${MACHINE_DIR}"
    fi
}

function open_shell() {
    require_root
    # Provide an interactive shell inside container
    machinectl shell ${CONTAINER_NAME} /bin/bash
}

function show_status() {
    machinectl list
}

function install_services() {
    require_root
    echo "Installing mariadb-server and redis-server (noninteractive) inside ${CONTAINER_NAME}..."
    # Use machinectl shell for commands
    machinectl shell ${CONTAINER_NAME} /bin/bash -lc "DEBIAN_FRONTEND=noninteractive apt-get update && apt-get install -y mariadb-server redis-server"

    echo "Enabling and starting services inside container..."
    machinectl shell ${CONTAINER_NAME} /bin/bash -lc "systemctl enable --now mariadb && systemctl enable --now redis-server"

    echo "Services started. You can connect from the host by exposing ports or via machinectl shell."
    echo "Example: sudo lsof -i -P -n | grep mysqld (inside container) or machinectl shell ${CONTAINER_NAME} -- ss -ltnp"
}

function usage() {
    cat <<EOF
Usage: $0 <command>

Commands:
  create    Create the container filesystem (uses debootstrap)
  start     Start or boot the container
  install   Install mariadb-server and redis-server inside the container
  shell     Open interactive shell inside container (requires root)
  stop      Stop the container
  destroy   Remove container root filesystem
  status    Show machinectl list / status

Notes:
 - This helper requires a Linux host with systemd, systemd-nspawn and machinectl installed.
 - You must run most commands as root (sudo) because systemd-nspawn/machinectl requires elevated privileges.
 - The container uses the host kernel; this is not a full VM.
 - Intended for developer debugging and opt-in testing only.
EOF
}

if [[ $# -lt 1 ]]; then
    usage
    exit 1
fi

case "$1" in
    create)
        create_container
        ;;
    start)
        start_container
        ;;
    install)
        install_services
        ;;
    stop)
        stop_container
        ;;
    shell)
        open_shell
        ;;
    destroy)
        destroy_container
        ;;
    status)
        show_status
        ;;
    *)
        usage
        exit 2
        ;;
esac

exit 0
