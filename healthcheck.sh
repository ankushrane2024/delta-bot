#!/usr/bin/env bash
# Using python to ping the health endpoint since curl might not be in the slim image
python3 -c "import urllib.request, sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health').getcode() == 200 else 1)"
