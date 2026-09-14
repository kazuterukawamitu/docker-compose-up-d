#!/bin/bash
# Double-click in Finder (Mac). Always starts DRY_RUN. Never enables LIVE.
cd "$(dirname "$0")"
exec /usr/bin/env bash "./start.sh"
