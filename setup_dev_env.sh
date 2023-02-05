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


# venv
if [[ ! -d "./.venv" ]]; then
    print "Create python virtual environment"
    python3 -m venv .venv
fi

pip3 install -r requirements.txt


# git hook
print "Enable git hook for pre-commit"
git config core.hooksPath .github/hooks


#



print "Done"