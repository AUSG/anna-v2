.PHONY: setup-local-env
setup-local-env:
	. .meta/develop/setup_local_env.sh

.PHONY: lint_fmt_test
lint_fmt_test:
	. .meta/develop/lint_fmt_test.sh

.PHONY: run-local
run-local:
	source .venv/bin/activate && python src/anna.py

.PHONY: deploy
deploy: lint_fmt_test
	fly deploy --config .meta/deploy/fly.toml --dockerfile .meta/deploy/Dockerfile --ignorefile .meta/deploy/.dockerignore

.PHONY: run-deploy
run-deploy:
	python src/anna.py
