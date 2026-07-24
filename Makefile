PYTHON ?= python
SAMPLE_DIR ?= /tmp/villa-floorplan-cad-sample

.PHONY: install test sample validate clean

install:
	$(PYTHON) -m pip install -r requirements.txt

test:
	$(PYTHON) -m pytest -q

sample:
	rm -rf $(SAMPLE_DIR)
	$(PYTHON) scripts/create_project.py --root /tmp --project-dir $(notdir $(SAMPLE_DIR)) --profile generic-metric --generate

validate:
	$(PYTHON) scripts/validate_plan.py $(SAMPLE_DIR)/output/plan.json --output $(SAMPLE_DIR)/output/validation.json --fail-on error

clean:
	rm -rf .pytest_cache scripts/__pycache__ tests/__pycache__
