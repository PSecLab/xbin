# xbin developer / test targets.
# Run from the repo root. See docs/e2e_testing.md for the full walkthrough.
#
# Nothing here names a plugin or a tier: base images, staged fixtures and e2e
# tiers all come from what is installed under plugins/.

# Interpreter used to create .venv. Override if your python3 is >= 3.11:
#   make setup PYTHON=/usr/bin/python3.12
PYTHON ?= python3
VENV   := .venv
PY     := $(VENV)/bin/python

# Every shared base-image bundle and every plugin-provided fixture stager.
# $(sort) dedupes: plugins/*/*/ already covers plugins/_bases/<bundle>/, so
# without it a bundle's stage.sh would be run twice.
BASES   := $(sort $(wildcard plugins/_bases/*/build.sh))
STAGERS := $(sort $(wildcard plugins/*/*/stage.sh) $(wildcard plugins/_bases/*/stage.sh))

.PHONY: help setup preflight test tiers bases stage e2e clean

help:
	@echo "targets:"
	@echo "  setup        create .venv + pip install -e . pytest"
	@echo "  preflight    check readiness (core + plugin-contributed checks)"
	@echo "  test         fast Docker-free pytest lane"
	@echo "  tiers        list the e2e tiers the installed plugins define"
	@echo "  bases        build every plugins/_bases/*/build.sh base image"
	@echo "  stage        run every plugin's stage.sh (test fixtures -> uploads/)"
	@echo "  e2e          full-stack run; TIER=<name> (default: smoke)"
	@echo "  clean        remove xbin-worker-* containers"
	@echo ""
	@echo "  base images available: $(if $(BASES),$(BASES),none)"

setup:
	$(PYTHON) -m venv $(VENV)
	$(PY) -m pip install --upgrade pip
	$(PY) -m pip install -e . pytest

preflight:
	scripts/preflight.sh --tier $(or $(TIER),smoke)

test:
	$(PY) -m pytest

tiers:
	@$(PY) scripts/e2e_driver.py --list-tiers

bases:
	@if [ -z "$(BASES)" ]; then echo "no plugins/_bases/*/build.sh found"; fi
	@for b in $(BASES); do echo "[*] $$b"; "$$b" || exit 1; done

stage:
	@if [ -z "$(STAGERS)" ]; then echo "no plugin stage.sh found"; fi
	@for s in $(STAGERS); do echo "[*] $$s"; "$$s" || exit 1; done

e2e:
	scripts/e2e.sh $(or $(TIER),smoke)

clean:
	-docker rm -f $$(docker ps -aq --filter name=xbin-worker-) 2>/dev/null || true
