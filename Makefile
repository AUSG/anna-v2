.PHONY: setup_local_env
setup_local_env:
	. .meta/develop/setup_local_env.sh

.PHONY: lint_fmt_test
lint_fmt_test:
	. .meta/develop/lint_fmt_test.sh

.PHONY: run_local
run_local:
	source venv/bin/activate && python src/anna.py

.PHONY: open_port
open_port:
	npx tunnelmole 8080

.PHONY: deploy
deploy: lint_fmt_test
	fly deploy --config .meta/deploy/fly.toml --dockerfile .meta/deploy/Dockerfile --ignorefile .meta/deploy/.dockerignore

.PHONY: run_deploy
run_deploy:
	python src/anna.py
