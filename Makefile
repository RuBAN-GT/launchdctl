.PHONY: format lint check install brew-bump

format:
	ruff format src
	ruff check --fix src

lint:
	ruff check src

check: lint
	python -m compileall -q src

install:
	pip install -e ".[dev]"

brew-bump:
	@chmod +x scripts/brew-formula-bump.sh
	@./scripts/brew-formula-bump.sh $(VERSION)
