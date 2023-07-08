.PHONY: setup-local-env
setup-local-env:
	. .meta/develop/setup_local_env.sh

.PHONY: lint_fmt_test
lint_fmt_test:
	. .meta/develop/lint_fmt_test.sh

.PHONY: deploy
deploy: lint_fmt_test
	fly deploy --config .meta/deploy/fly.toml --dockerfile .meta/deploy/Dockerfile --ignorefile .meta/deploy/.dockerignore

