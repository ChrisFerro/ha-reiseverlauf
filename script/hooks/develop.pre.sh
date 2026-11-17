# shellcheck shell=bash
# Sourced by script/develop before Home Assistant starts.

# Writable media folder inside the checkout, independent of the folder name
# the repository was cloned into (config/configuration.yaml reads it).
mkdir -p "${PWD}/config/media"
export REISEVERLAUF_MEDIA_DIR="${PWD}/config/media"
