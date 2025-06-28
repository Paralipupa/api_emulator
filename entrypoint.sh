#!/bin/bash

set -e

run_server () {
  python app.py
}

run_server_debug () {
  python -m debugpy --listen 0.0.0.0:5694 app.py
}


case "$1" in
  run_server) "$@"; exit;;
  run_server_debug) "$@"; exit;;
  *) exec "$@"; exit;;
esac
