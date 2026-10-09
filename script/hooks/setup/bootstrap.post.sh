# shellcheck shell=bash
# script/hooks/setup/bootstrap.post.sh: Install the integration's runtime dependencies.
#
# Workaround: script/setup/bootstrap skips requirements.txt because its `grep -qv` check never matches.
# https://github.com/jpawlowski/hacs.integration_blueprint/issues/99

log_header "Installing runtime dependencies (requirements.txt)"
uv pip install --requirement requirements.txt
log_success "Runtime dependencies installed"
