#!/usr/bin/env bash
echo "Sending SIGTERM to ARES ServiceRunner..."
pkill -f "python3 -m hedge.deployment.service_runner"
echo "Shutdown signal sent."
