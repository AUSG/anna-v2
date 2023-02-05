#!/usr/bin/env bash


####################################
#              util
####################################

## args: 
##  first parameter: message
print () {
    GREEN='\033[0;32m'
    NO_COLOR='\033[0m'
    echo -e "${GREEN}$1$NO_COLOR"
}
# ~ color scheme


####################################
#              main
####################################

print "Setup started"

# venv
if [[ ! -d "./.venv" ]]; then
    print "Create python virtual environment"
    python3 -m venv .venv
fi

print "Enable python virtual environment"
source ./.venv/bin/activate

print "Install python packages"
pip3 install -r requirements.txt --quiet

# git submodule
print "Update submodules (repository for environment variables)"
git submodule update --init --recursive

# git hook
print "Enable git hook for pre-commit"
git config core.hooksPath .github/hooks

print "Setup finished"
