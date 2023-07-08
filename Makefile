.PHONY: setup-local-env
setup-local-env:
	. .meta/develop/setup_local_env.sh

.PHONY: deploy
deploy: lint_fmt_test
	fly deploy --config .meta/deploy/fly.toml
