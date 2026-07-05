.PHONY: install test web mcp cli play docker-build docker-run deploy clean

VENV := .venv
PY := $(VENV)/bin/python
PIP := $(VENV)/bin/pip

install:
	python3 -m venv $(VENV)
	$(PIP) install -q -e ".[test]"

test:
	$(PY) -m pytest -p no:warnings

web:            ## browser UI on :8080
	$(PY) -m web.serve

mcp:            ## MCP server on :8000
	$(PY) -m uvicorn mcp_server.server:app --host 0.0.0.0 --port 8000

play:           ## terminal game
	$(PY) -m cli.main new-game

skills:         ## list agent skills (Agents CLI)
	$(PY) -m agents.skills_cli list

docker-build:
	docker build -t road-to-ussuri .

docker-run:
	docker run --rm -p 8080:8080 -e GROQ_API_KEY=$(GROQ_API_KEY) road-to-ussuri

deploy:         ## Cloud Run (needs PROJECT_ID + GROQ_API_KEY)
	./deploy/deploy_cloud_run.sh

clean:
	rm -rf $(VENV) data/*.db data/*.log .pytest_cache
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
