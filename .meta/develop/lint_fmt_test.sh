#!/usr/bin/env bash
set -e # exit on first error
set -x # print commands

pytest -c .meta/develop/pytest.ini --cov=./