# 개발 환경 setup
.PHONY: setup
setup:
	./scripts/setup_local_env.sh

.PHONY: run-local
run-local:
	export LOCAL=True && python3 src/anna.py

.PHONY: run-prod
run:
	python3 src/anna.py

.PHONY: test
test:
	pytest --cov=./
