# ExTetris build targets.  Usage: make <target>   (PYTHON=python3.12 make test, etc.)
PYTHON ?= python3
CLI     = $(PYTHON) v2_platform_release/cli.py
VARIANTS = $(wildcard variants/*.toml)
GAMES  ?= 100

.PHONY: all test verify validate simulate package notebook-check play clean

all: test validate package

test:            ## unit + integration tests (v1 core and v2 platform)
	$(PYTHON) -m pytest v1_core_system v2_platform_release -q

verify:          ## standalone verification scripts (piece hierarchy, v0.5 failure proof)
	$(PYTHON) v1_core_system/verify_piece.py
	$(PYTHON) v0.5_failed_attempt/verify_v05.py

validate:        ## validate every variant in variants/
	@for v in $(VARIANTS); do $(CLI) validate $$v || exit 1; done

simulate:        ## balance check every variant (GAMES=100)
	@for v in $(VARIANTS); do $(CLI) simulate $$v --games $(GAMES) || exit 1; done

package:         ## build dist/<variant>-<version>.zip for every variant
	@for v in $(VARIANTS); do $(CLI) package $$v --pyinstaller || exit 1; done

notebook-check:  ## make sure the Designer Studio notebook is valid JSON / nbformat 4
	$(PYTHON) -c "import json; nb = json.load(open('v2_platform_release/Variant_Designer_Studio.ipynb')); assert nb['nbformat'] == 4; print('notebook OK:', len(nb['cells']), 'cells')"

play:            ## make play VARIANT=variants/corner_chaos.toml
	$(CLI) play $(or $(VARIANT),variants/classic_1984.toml)

clean:
	rm -rf dist .pytest_cache v1_core_system/__pycache__ v2_platform_release/__pycache__
