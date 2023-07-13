.PHONY: setup_local_env
setup_local_env:
	. .meta/develop/setup_local_env.sh

.PHONY: lint_fmt_test
lint_fmt_test:
	source venv/bin/activate && .meta/develop/lint_fmt_test.sh

.PHONY: test
test:
	source venv/bin/activate && .meta/develop/lint_fmt_test.sh --test-only

.PHONY: update_submodule
update_submodule:
	git submodule update --recursive --remote

.PHONY: run_local
run_local:
	source venv/bin/activate && cd src && python anna.py

.PHONY: open_port
open_port:
	npx tunnelmole 8080

.PHONY: deploy
deploy: update_submodule lint_fmt_test
	fly deploy --config .meta/deploy/fly.toml --dockerfile .meta/deploy/Dockerfile --ignorefile .meta/deploy/.dockerignore

.PHONY: run_deploy
run_deploy:
	cd src && python anna.py
