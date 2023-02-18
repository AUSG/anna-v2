#!/usr/bin/env bash


####################################
#              util
####################################

## args: 
##  first parameter: message
## warning:
##  if you use `print` instead of `_print`, your terminal
##  will be corrupted after this script is executed
_print () {
    GREEN='\033[0;32m'
    NO_COLOR='\033[0m'
    echo -e "${GREEN}$1$NO_COLOR"
}
# ~ color scheme


####################################
#              main
####################################

_print "Setup started"

# venv
if [[ ! -d "./.venv" ]]; then
    _print "Create python virtual environment"
    python3 -m venv .venv
fi

_print "Enable python virtual environment"
source ./.venv/bin/activate

_print "Install python packages"
pip3 install -r requirements.txt --quiet

# git submodule
_print "Update submodules (repository for environment variables)"
git submodule update --init --recursive

# git hook
_print "Enable git hook for pre-commit"
git config core.hooksPath .github/hooks

_print "Setup finished"
