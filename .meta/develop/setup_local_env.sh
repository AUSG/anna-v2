#!/usr/bin/env bash
set -e # exit on first error

####################################
#              util
####################################

## args:
##  first parameter: message
## warning:
##  if you use `print` instead of `_print`, your terminal
##  will be corrupted after this script is executed
_print() {
  GREEN='\033[0;32m'
  NO_COLOR='\033[0m'
  echo "${GREEN}$1$NO_COLOR"
}

####################################
#              main
#
# - make venv
# - git submodules
# - git hooks
####################################


_print "Setup started..."

if [[ ! -d "./venv" ]]; then
  _print "Create python virtual environment"
  python3 -m venv venv
fi
source venv/bin/activate

_print "Upgrade pip"
pip install --upgrade pip -q

_print "Install python packages"
pip install -r requirements.txt --quiet

_print "Initialize git submodules"
git submodule update --init --recursive

_print "Enable git hook for pre-commit"
git config core.hooksPath .github/hooks

_print "Setup finished..."

_print ""
_print "Run the following command to enable virtual environment:"
_print ""
_print "source venv/bin/activate"
