.PHONY: setup run docker seed test clean oidc venv

# Setup virtual environment and install dependencies
setup: venv
	@echo "Installing dependencies..."
	venv/bin/pip install --upgrade pip
	venv/bin/pip install -r requirements.txt
	@echo "Setup complete! Activate with: source venv/bin/activate"

# Create virtual environment
venv:
	@if [ ! -d "venv" ]; then \
		echo "Creating virtual environment..."; \
		python3 -m venv venv; \
	fi

run:
	uvicorn app.main:app --reload --host 0.0.0.0 --port 8080

oidc:
	venv/bin/python scripts/mock_oidc.py

docker:
	docker build -t secure-rag-demo .

docker-run:
	docker run -p 8080:8080 --env-file .env secure-rag-demo

seed:
	python scripts/seed.py --url http://localhost:8080 --token $(TOKEN) --tenant $(TENANT)

seed-acme:
	venv/bin/python scripts/seed_acme_data.py

verify-seed:
	venv/bin/python scripts/verify_seed.py

reset-collection:
	venv/bin/python scripts/reset_collection.py

test:
	pytest -q

test-verbose:
	pytest -v

test-full:
	venv/bin/python scripts/test_full.py

test-comprehensive:
	venv/bin/python scripts/test_and_fix.py

setup-vector:
	@echo "Setting up vector-enabled collection and testing vector search..."
	venv/bin/python scripts/setup_and_test_vector.py

test-vector:
	@echo "Testing vector search functionality..."
	venv/bin/python scripts/test_vector_search.py

demo:
	@echo "Running demo..."
	venv/bin/python scripts/demo.py

seed-restricted:
	venv/bin/python scripts/seed_restricted.py

clean:
	find . -type d -name __pycache__ -exec rm -r {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type d -name ".pytest_cache" -exec rm -r {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -r {} + 2>/dev/null || true

