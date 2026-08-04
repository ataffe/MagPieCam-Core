#!/bin/sh
set -e

moto_server -H 0.0.0.0 -p 5000 &
MOTO_PID=$!

python /app/init_resources.py

wait "$MOTO_PID"
