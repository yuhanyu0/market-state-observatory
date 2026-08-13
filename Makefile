.PHONY: setup dev test lint typecheck validate audit build publish-data release demo manifest

setup:
	python -m pip install -e ".[dev]"
	npm ci

dev:
	npm run dev -- --host 127.0.0.1

test:
	pytest
	npm test

lint:
	ruff check src tests scripts

typecheck:
	mypy src
	npm run build

validate:
	python scripts/validate_repo.py

audit:
	python scripts/audit_publication.py
	python scripts/check_secret_patterns.py
	python scripts/check_site_links.py

build:
	npm run build

publish-data:
	python scripts/publish_private_snapshot.py "$(PRIVATE_QUALITY)" --push

demo:
	python scripts/run_synthetic_demo.py

manifest:
	python scripts/build_manifest.py

release: test lint typecheck validate audit demo build manifest
