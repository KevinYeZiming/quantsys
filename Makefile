.PHONY: help setup data-update factors backtest signals test lint clean
.PHONY: api dashboard cred-save cred-list cred-delete deploy

STRATEGY ?= multifactor
START   ?= 2018-01-01
END     ?= 2023-12-31

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

setup: ## Install dependencies and verify environment
	pip install -r requirements.txt
	python3 scripts/validate_setup.py

data-update: ## Update data incrementally
	python3 scripts/update_data.py

data-full: ## Full historical data download
	python3 scripts/update_data.py --full --start 20150101

factors: ## Calculate all factors
	python3 scripts/calc_factors.py

backtest: ## Run strategy backtest (STRATEGY=multifactor START= END=)
	python3 scripts/run_backtest.py --strategy $(STRATEGY) --start $(START) --end $(END)

signals: ## Generate today's trading signals
	python3 scripts/generate_signals.py

# -- API & Dashboard ------------------------------------------------

api: ## Start FastAPI backend server
	uvicorn quantsys.api.server:app --host 0.0.0.0 --port 8888 --reload

dashboard: ## Start Streamlit dashboard
	streamlit run quantsys/web/dashboard.py --server.port 8501

# -- Credential management ------------------------------------------

cred-save: ## Save encrypted broker credentials (BROKER=galaxy USER=xxx PASS=xxx)
	python3 -c "\
import sys; sys.path.insert(0, '.'); \
from quantsys.security import CredentialManager; \
mgr = CredentialManager(); \
mgr.save_broker_credentials('$(BROKER)', '$(USER)', '$(PASS)'); \
print('Credentials saved for $(BROKER)')"

cred-list: ## List stored broker credentials
	python3 -c "\
import sys; sys.path.insert(0, '.'); \
from quantsys.security import CredentialManager; \
mgr = CredentialManager(); \
brokers = mgr.list_brokers(); \
print('Stored credentials:', brokers if brokers else '(none)')"

cred-delete: ## Delete broker credentials (BROKER=galaxy)
	python3 -c "\
import sys; sys.path.insert(0, '.'); \
from quantsys.security import CredentialManager; \
mgr = CredentialManager(); \
ok = mgr.delete_broker_credentials('$(BROKER)'); \
print('Deleted' if ok else 'Not found')"

# -- Dev tools ------------------------------------------------------

test: ## Run tests
	pytest tests/ -v

test-fast: ## Run fast tests only
	pytest tests/ -v -x -m "not slow"

lint: ## Lint code
	ruff check quantsys/ scripts/ tests/

lint-fix: ## Lint and auto-fix
	ruff check quantsys/ scripts/ tests/ --fix

notebook: ## Start Jupyter lab
	jupyter lab notebooks/

clean: ## Clean generated files
	rm -rf reports/ __pycache__ .pytest_cache
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true

deploy: ## Full deploy: install deps, download data, start services
	@echo "=== Installing dependencies ==="
	pip install -r requirements.txt
	@echo "=== Updating data ==="
	python3 scripts/update_data.py
	@echo "=== Starting API + Dashboard ==="
	@echo "API:     http://localhost:8888/docs"
	@echo "Dashboard: http://localhost:8501"
