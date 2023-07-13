#!/usr/bin/env bash
set -e # exit on first error
set -x # print commands

if [[ "$1" == "--test-only" ]]; then
    echo "Running tests only"
    PYTHONPATH=src pytest --rootdir=./test --cov=./src --cov-report=html -c .meta/develop/pytest.ini
    exit 0
fi

black src
pylint --rcfile .meta/develop/pylint.toml src
PYTHONPATH=src pytest --rootdir=./test --cov=./src --cov-report=html -c .meta/develop/pytest.ini
