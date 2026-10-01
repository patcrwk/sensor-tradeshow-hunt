# 1. DETECT OPERATING SYSTEM & ADJUST PATHS/COMMANDS
ifeq ($(OS),Windows_NT)
    PY ?= python
    VPY = $(VENV)/Scripts/python.exe
    RM = rmdir /s /q
    # Windows Git Bash handles standard background execution differently for complex traps
    IS_WINDOWS = true
else
    PY ?= python3
    VPY = $(VENV)/bin/python
    RM = rm -rf
    IS_WINDOWS = false
endif

VENV = .venv
export PYTHONPATH := $(CURDIR)

.PHONY: setup engine web dev show test synth mock tune kiosk clean

# 2. TARGETS
setup: ## create the Python venv and install web dependencies
	if [ ! -d "$(VENV)" ]; then $(PY) -m venv $(VENV); fi
	$(VPY) -m pip install -q -r engine/requirements.txt
	cd web && npm install

engine: ## API on http://localhost:8000
	$(VPY) -m uvicorn engine.api.app:app --host 0.0.0.0 --port 8000

web: ## web app on http://localhost:3000
	cd web && npm run dev

dev: ## both services (Ctrl+C stops both)
ifeq ($(IS_WINDOWS),true)
	@echo "Starting dev servers (Press Ctrl+C to exit)..."
	$(VPY) -m uvicorn engine.api.app:app --host 0.0.0.0 --port 8000 --reload --reload-dir engine & \
	cd web && npm run dev
else
	@trap 'kill 0' INT TERM; \
	$(VPY) -m uvicorn engine.api.app:app --host 0.0.0.0 --port 8000 --reload --reload-dir engine & \
	(cd web && npm run dev) & \
	wait
endif

show: ## production build of the web app, then both services (use at the booth)
	cd web && npm run build
ifeq ($(IS_WINDOWS),true)
	@echo "Starting production view..."
	$(VPY) -m uvicorn engine.api.app:app --host 0.0.0.0 --port 8000 & \
	cd web && npm run start
else
	@trap 'kill 0' INT TERM; \
	$(VPY) -m uvicorn engine.api.app:app --host 0.0.0.0 --port 8000 & \
	(cd web && npm run start) & \
	wait
endif

test: ## engine tests (parser, synthetic pipeline in all modes, API, explorer)
	$(VPY) -m pytest -q

synth: ## synthetic survey + participant files in fixtures/synthetic
	$(VPY) -m engine.synthetic.cli --out fixtures/synthetic --gps outdoor
	$(VPY) -m engine.synthetic.cli --out fixtures/synthetic --gps dropout --holders --serial 91001

mock: ## 1 survey + 5 participants (sensors 90001-90005) in fixtures/mock for testing on the dev server
	$(RM) fixtures/mock 2>/dev/null || true
	$(VPY) -m engine.synthetic.cli --out fixtures/mock --gps outdoor --participants 5 --serial 90001 --seed 42 --start-in-hours 24 --zips-only

tune: ## make tune FILE=path/to/file.IDE [ARGS=--survey]
	$(VPY) -m engine.tune $(FILE) $(ARGS)

kiosk: ## open the display in a full-screen browser (macOS, Chrome)
ifeq ($(IS_WINDOWS),true)
	start chrome --kiosk --app=http://localhost:3000/display
else
	open -a "Google Chrome" --args --kiosk --app=http://localhost:3000/display
endif

clean:
	$(RM) data 2>/dev/null || true
	$(RM) fixtures/synthetic 2>/dev/null || true