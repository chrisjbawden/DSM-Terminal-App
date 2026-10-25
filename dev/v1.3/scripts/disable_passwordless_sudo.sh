#!/bin/sh

set -eu

SUDOERS_FILE="/etc/sudoers.d/dsm-terminal"

rm -f "${SUDOERS_FILE}"

printf 'Disabled passwordless sudo for sc-dsm-terminal\n'
