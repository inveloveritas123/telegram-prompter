PYTHON  := .venv/bin/python
RUFF    := .venv/bin/ruff
MYPY    := .venv/bin/mypy
BANDIT  := .venv/bin/bandit

.PHONY: lint format typecheck sast test gates

lint:
	$(RUFF) check admin orchestrator prompter

format:
	$(RUFF) format admin orchestrator prompter

typecheck:
	PYTHONPATH=zukunftsbund-bottests:. $(MYPY) admin orchestrator prompter

sast:
	$(BANDIT) -r admin orchestrator prompter --ini .bandit

test:
	PYTHONPATH=zukunftsbund-bottests:. $(PYTHON) -m pytest -q prompter/tests
	PYTHONPATH=. $(PYTHON) -m pytest -q orchestrator/tests admin/tests
	( cd zukunftsbund-bottests && PYTHONPATH=. ../$(PYTHON) -m pytest -q )

gates: lint typecheck sast test
