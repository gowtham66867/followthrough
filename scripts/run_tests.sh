#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
TASK_TEST_HOME=$(mktemp -d)
trap 'rm -rf "$TASK_TEST_HOME"' EXIT
unset NEBIUS_API_KEY NEBIUS_TOKEN_FACTORY_API_KEY GOOGLE_CLIENT_SECRET
export HERMES_HOME="$TASK_TEST_HOME" TZ=UTC LANG=C.UTF-8
if [ -x .venv/bin/python ]; then
  exec_python=.venv/bin/python
elif [ -n "${HERMES_PYTHON:-}" ]; then
  exec_python="$HERMES_PYTHON"
else
  exec_python=python3
fi
for test_file in tests/test_*.py; do
  "$exec_python" -m pytest -c /dev/null --rootdir=. -p no:cacheprovider "$test_file" "$@"
done
