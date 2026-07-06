#!/usr/bin/env bash
set -e
echo "Starting ARES ServiceRunner..."
# Ensure data and logs directories exist
mkdir -p /app/data /app/logs
exec python3 -m hedge.deployment.service_runner
