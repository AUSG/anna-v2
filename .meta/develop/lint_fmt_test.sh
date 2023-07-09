#!/usr/bin/env bash
set -e # exit on first error
set -x # print commands

black src
pylint --rcfile .meta/develop/pylint.toml src
PYTHONPATH=src pytest --rootdir=./src --cov=./test -c .meta/develop/pytest.ini
