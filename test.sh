#!/bin/bash

set -e

python chess-server.py --port 5000 &
PID=$!

trap "kill -n 1 $PID" EXIT

timeout 10 bash -c "while ! timeout 1 curl -s localhost:5000 -o /dev/null ; do sleep 1 ; done"

[[ $(curl -s -w "%{http_code}" "localhost:5000" -o /dev/null) == 200 ]]
