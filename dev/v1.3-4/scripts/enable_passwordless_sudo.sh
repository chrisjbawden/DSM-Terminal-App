#!/bin/sh

set -eu

SUDOERS_DIR="/etc/sudoers.d"
SUDOERS_FILE="${SUDOERS_DIR}/dsm-terminal"

mkdir -p "${SUDOERS_DIR}"
printf '%s\n' 'sc-dsm-terminal ALL=(ALL) NOPASSWD: ALL' > "${SUDOERS_FILE}"
chmod 440 "${SUDOERS_FILE}"

printf 'Enabled passwordless sudo for sc-dsm-terminal via %s\n' "${SUDOERS_FILE}"
