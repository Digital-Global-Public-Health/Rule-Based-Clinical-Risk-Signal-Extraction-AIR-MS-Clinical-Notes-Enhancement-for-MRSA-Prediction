#!/usr/bin/env bash
#
# Deploy INCEpTION as a self-contained standalone application.
#
# This downloads the official standalone executable JAR from GitHub Releases
# and runs it with an embedded server and embedded database. No Docker and no
# external MySQL/MariaDB is required, which makes it the right choice for
# restricted/sandboxed environments where container image CDNs are blocked.
#
# Usage:
#   ./run-standalone.sh            # download (if needed) and run on port 8080
#   INCEPTION_PORT=9090 ./run-standalone.sh
#
# Requires: Java 17+ (Java 21 recommended) and curl.
#
set -euo pipefail

INCEPTION_VERSION="${INCEPTION_VERSION:-40.6}"
INCEPTION_PORT="${INCEPTION_PORT:-8080}"
# Where INCEpTION stores its data (repository, embedded DB, settings, logs).
INCEPTION_HOME="${INCEPTION_HOME:-$HOME/inception-home}"
JAVA_OPTS="${JAVA_OPTS:--Xmx2g -Djava.awt.headless=true}"

JAR_NAME="inception-app-webapp-${INCEPTION_VERSION}-standalone.jar"
JAR_URL="https://github.com/inception-project/inception/releases/download/inception-${INCEPTION_VERSION}/${JAR_NAME}"
JAR_DIR="${JAR_DIR:-$(dirname "$0")/dist}"
JAR_PATH="${JAR_DIR}/${JAR_NAME}"

mkdir -p "${JAR_DIR}" "${INCEPTION_HOME}"

if [[ ! -f "${JAR_PATH}" ]]; then
  echo ">> Downloading ${JAR_NAME} ..."
  curl -fSL --retry 4 --retry-delay 2 -o "${JAR_PATH}" "${JAR_URL}"
fi

echo ">> INCEPTION_HOME = ${INCEPTION_HOME}"
echo ">> Starting INCEpTION ${INCEPTION_VERSION} on http://localhost:${INCEPTION_PORT}/"
echo ">> Default first-run login: admin / admin (you will be asked to change it)"

export INCEPTION_HOME
exec java ${JAVA_OPTS} \
  -Dserver.port="${INCEPTION_PORT}" \
  -jar "${JAR_PATH}"
