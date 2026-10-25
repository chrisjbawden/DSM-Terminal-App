#!/bin/sh

set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname "$0")" && pwd -P)
PKG_DIR=$(CDPATH= cd -- "${SCRIPT_DIR}/../.." && pwd -P)
PKG_NAME=$(basename "${PKG_DIR}")
SESSION_DIR="/tmp/${PKG_NAME}-sessions"
HOME_DIR="/tmp/${PKG_NAME}-home"
AUTH_CGI="/usr/syno/synoman/webman/modules/authenticate.cgi"

mkdir -p "${SESSION_DIR}" "${HOME_DIR}"

json_escape() {
    printf '%s' "$1" | awk '
        BEGIN {
            ORS = "";
            print "\"";
        }
        {
            gsub(/\\/,"\\\\");
            gsub(/"/,"\\\"");
            gsub(/\r/,"\\r");
            gsub(/\t/,"\\t");
            if (NR > 1) {
                printf "\\n";
            }
            printf "%s", $0;
        }
        END {
            print "\"";
        }
    '
}

send_json() {
    printf 'Content-Type: application/json\r\n'
    printf 'Cache-Control: no-store\r\n\r\n'
    printf '%s\n' "$1"
}

trim_line() {
    printf '%s' "$1" | tr -d '\r' | awk 'NF { print; exit }'
}

url_decode() {
    printf '%b' "$(printf '%s' "$1" | sed 's/+/ /g; s/%/\\x/g')"
}

resolve_user() {
    if [ -n "${REMOTE_USER:-}" ]; then
        trim_line "${REMOTE_USER}"
        return 0
    fi

    auth_output=$(
        HTTP_COOKIE="${HTTP_COOKIE:-}" \
        REMOTE_ADDR="${REMOTE_ADDR:-}" \
        SERVER_ADDR="${SERVER_ADDR:-}" \
        REQUEST_METHOD="${REQUEST_METHOD:-GET}" \
        QUERY_STRING="${QUERY_STRING:-}" \
        "${AUTH_CGI}" 2>/dev/null || true
    )
    auth_output=$(trim_line "${auth_output}")
    if [ -n "${auth_output}" ]; then
        printf '%s\n' "${auth_output}"
        return 0
    fi

    if [ -n "${HTTP_COOKIE:-}" ]; then
        printf '%s\n' "dsm-session"
        return 0
    fi

    return 1
}

session_file() {
    kind=$1
    sid=$2
    printf '%s/%s.%s' "${SESSION_DIR}" "${sid}" "${kind}"
}

load_request() {
    body=""
    if [ "${REQUEST_METHOD:-GET}" = "POST" ]; then
        length=${CONTENT_LENGTH:-0}
        if [ "${length}" -gt 0 ] 2>/dev/null; then
            body=$(dd bs=1 count="${length}" 2>/dev/null)
        fi
    else
        body=${QUERY_STRING:-}
    fi

    old_ifs=$IFS
    IFS='&'
    for pair in $body; do
        IFS=$old_ifs
        key=$(url_decode "${pair%%=*}")
        value=$(url_decode "${pair#*=}")
        case "$key" in
            action) ACTION=$value ;;
            sid) SID=$value ;;
            cmd) CMD=$value ;;
        esac
        IFS='&'
    done
    IFS=$old_ifs
}

ACTION=""
SID=""
CMD=""
load_request

USER_NAME=$(resolve_user || true)
if [ -z "${USER_NAME}" ]; then
    send_json '{"ok":false,"error":"DSM authentication failed"}'
    exit 0
fi

case "${ACTION}" in
    init)
        SID=$(printf '%s:%s:%s\n' "$(date +%s)" "$$" "${USER_NAME}" | cksum | awk '{print $1}')
        printf '%s\n' "${HOME_DIR}" > "$(session_file cwd "${SID}")"
        send_json "{\"ok\":true,\"sid\":$(json_escape "${SID}"),\"cwd\":$(json_escape "${HOME_DIR}"),\"user\":$(json_escape "${USER_NAME}")}"
        ;;
    run)
        case "${SID}" in
            ''|*[!A-Za-z0-9._-]*)
                send_json '{"ok":false,"error":"Invalid session id"}'
                exit 0
                ;;
        esac

        cwd_file=$(session_file cwd "${SID}")
        if [ ! -f "${cwd_file}" ]; then
            send_json '{"ok":false,"error":"Session not found"}'
            exit 0
        fi

        cwd=$(cat "${cwd_file}")
        marker="__DSM_TERMINAL_PWD__$$"
        tmp_file=$(mktemp "${SESSION_DIR}/command.XXXXXX")
        status=0

        if ! sh -c '
            cd "$1" 2>/dev/null || cd "$4"
            eval "$2"
            status=$?
            printf "\n%s%s\n" "$3" "$PWD"
            exit "$status"
        ' sh "${cwd}" "${CMD}" "${marker}" "${HOME_DIR}" >"${tmp_file}" 2>&1; then
            status=$?
        fi

        new_cwd=$(awk -v marker="${marker}" 'index($0, marker) == 1 { print substr($0, length(marker) + 1) }' "${tmp_file}" | tail -n 1)
        if [ -n "${new_cwd}" ]; then
            printf '%s\n' "${new_cwd}" > "${cwd_file}"
        else
            new_cwd=${cwd}
        fi

        command_output=$(sed "/^${marker}/d" "${tmp_file}")
        rm -f "${tmp_file}"

        send_json "{\"ok\":true,\"cwd\":$(json_escape "${new_cwd}"),\"output\":$(json_escape "${command_output}"),\"exit_status\":${status}}"
        ;;
    reset)
        case "${SID}" in
            ''|*[!A-Za-z0-9._-]*) ;;
            *)
                rm -f "$(session_file cwd "${SID}")"
                ;;
        esac
        send_json '{"ok":true}'
        ;;
    *)
        send_json '{"ok":false,"error":"Unsupported action"}'
        ;;
esac
