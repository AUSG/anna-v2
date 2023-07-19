## Local Environment Setup

.PHONY: _set_hooks
_set_hooks:
	git config core.hooksPath .github/hooks

.PHONY: _update_submodule
_update_submodule:
	git submodule update --recursive --remote

.PHONY: setup_local_env
setup_local_env: _set_hooks _update_submodule
	pip install poetry

.PHONY: wakeup_anna
wakeup_anna:
	poetry install && cd src && poetry run python anna.py

.PHONY: open_port
open_port:
	npx tunnelmole 8080



## CI

.PHONY: _lintfmt
_lintfmt:
	poetry run black src/
	poetry run ruff src/

.PHONY: _test
_test:
	PYTHONPATH=src poetry run pytest --rootdir=./test --cov=./src --cov-report=html -c .meta/develop/pytest.ini

.PHONY: ci
ci: _lintfmt _test



## Deployment

.PHONY: deploy_local
deploy_local: _update_submodule ci
	poetry export -f requirements.txt --without-hashes -o requirements.txt
	fly deploy --config .meta/deploy/fly.toml --dockerfile .meta/deploy/Dockerfile --ignorefile .meta/deploy/.dockerignore

.PHONY: deploy_remote
deploy_remote: ci
	fly deploy --config .meta/deploy/fly.toml --dockerfile .meta/deploy/Dockerfile --ignorefile .meta/deploy/.dockerignore

.PHONY: wakeup_remote_anna
wakeup_remote_anna:
	cd src && python anna.py

