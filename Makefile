## Local Environment Setup

.PHONY: _set_hooks
_set_hooks:
	git config core.hooksPath .github/hooks

.PHONY: _update_submodule
_update_submodule:
	git submodule update --recursive --remote

.PHONY: setup_local_env
setup_local_env: _set_hooks _update_submodule
	uv sync --frozen


.PHONY: wakeup_anna
wakeup_anna:
	uv run --frozen gunicorn --config src/gunicorn_config.py --chdir src 'anna:create_app()' --bind 0.0.0.0:8080 --workers 1 --threads 8 --timeout 120

.PHONY: open_port
open_port:
	npx tunnelmole 8080



## CI

.PHONY: _lintfmt
_lintfmt:
	uv run --frozen ruff format --check
	uv run --frozen ruff check
	uv run --frozen ty check

.PHONY: _test
_test:
	uv run --frozen pytest --cov --cov-report=html

.PHONY: ci
ci: _lintfmt _test



## Deployment

.PHONY: deploy_local
deploy_local: _update_submodule ci
	fly version update
	fly deploy --config .meta/deploy/fly.toml --dockerfile .meta/deploy/Dockerfile

.PHONY: deploy_remote
deploy_remote: ci
	fly deploy --config .meta/deploy/fly.toml --dockerfile .meta/deploy/Dockerfile --remote-only
