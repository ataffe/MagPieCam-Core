#!/bin/sh
set -e

python /app/run_server.py &
MOTO_PID=$!

python /app/init_resources.py

wait "$MOTO_PID"
