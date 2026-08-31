.PHONY: help install run start stop restart status test clean logs apk deploy \
	deploy-start deploy-stop deploy-restart deploy-status deploy-logs

.DEFAULT_GOAL := help

VENV := .venv
UVICORN := $(VENV)/bin/uvicorn
PID_FILE := run/wemo_manager.pid
LOG_FILE := logs/wemo_manager.log
LOCK_FILE := wemo_manager.lock
DEPLOY_DIR := $(or $(WEMO_MANAGER_DEPLOY_DIR),./wemo-manager-deploy)

help: ## List available targets
	@grep -E '^[a-zA-Z_-]+:.*## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

install: ## Create .venv and install the package (incl. dev deps)
	python3 -m venv $(VENV)
	$(VENV)/bin/pip install -e ".[dev]"

run: ## Foreground dev server with autoreload (Ctrl-C to stop)
	$(UVICORN) app.main:app --reload --host 0.0.0.0 --port 8000

# LOCK_FILE is written by the app itself, so it tracks any running instance.
start: ## Start the server in the background
	@if [ -f $(LOCK_FILE) ] && kill -0 $$(cat $(LOCK_FILE)) 2>/dev/null; then \
		echo "Already running (pid $$(cat $(LOCK_FILE)))."; exit 1; \
	fi
	@mkdir -p run
	@nohup $(UVICORN) app.main:app --host 0.0.0.0 --port 8000 >/dev/null 2>&1 & \
		echo $$! > $(PID_FILE)
	@sleep 1
	@if kill -0 $$(cat $(PID_FILE)) 2>/dev/null; then \
		echo "Started (pid $$(cat $(PID_FILE)))."; \
	else \
		echo "Failed to start — check $(LOG_FILE)."; rm -f $(PID_FILE); exit 1; \
	fi

# The lock holder is the reload child; kill the uvicorn parent when there is one.
stop: ## Stop any running wemo-manager instance, force-killing if needed
	@if [ ! -f $(LOCK_FILE) ] || ! kill -0 $$(cat $(LOCK_FILE)) 2>/dev/null; then \
		echo "Not running."; rm -f $(PID_FILE); exit 0; \
	fi
	@PID=$$(cat $(LOCK_FILE)); \
	PARENT=$$(ps -o ppid= -p $$PID 2>/dev/null | tr -d ' '); \
	if ps -o command= -p $$PARENT 2>/dev/null | grep -q "uvicorn app.main:app"; then \
		TARGET=$$PARENT; \
	else \
		TARGET=$$PID; \
	fi; \
	kill $$TARGET 2>/dev/null; \
	for i in 1 2 3 4 5; do kill -0 $$PID 2>/dev/null || break; sleep 1; done; \
	if kill -0 $$PID 2>/dev/null; then \
		kill -9 $$TARGET $$PID 2>/dev/null; \
		echo "Didn't exit in 5s — force-killed (pid $$PID)."; \
	else \
		echo "Stopped (pid $$PID)."; \
	fi
	@rm -f $(PID_FILE)

restart: stop start ## Restart the background server

status: ## Show whether a wemo-manager instance is running (however it was started)
	@if [ -f $(LOCK_FILE) ] && kill -0 $$(cat $(LOCK_FILE)) 2>/dev/null; then \
		echo "Running (pid $$(cat $(LOCK_FILE)))."; \
	else \
		echo "Not running."; \
	fi

test: ## Run the test suite
	$(VENV)/bin/pytest

clean: ## Remove build artifacts, caches, and logs (leaves .venv alone)
	find . -name '__pycache__' -type d -prune -exec rm -rf {} +
	rm -rf .pytest_cache *.egg-info build logs run
	rm -f wemo_manager.lock app/static/wemo-manager.apk
	rm -rf mobile/android/build mobile/android/app/build mobile/android/capacitor-cordova-android-plugins/build

# Requires JDK 21 and the Android SDK. Falls back to common install locations.
APK_JAVA_HOME := $(or $(JAVA_HOME),$(shell /usr/libexec/java_home -v 21 2>/dev/null),$(wildcard /opt/homebrew/opt/openjdk@21/libexec/openjdk.jdk/Contents/Home),$(firstword $(wildcard /usr/lib/jvm/*-21-*)),$(wildcard /opt/jdk21))
APK_ANDROID_HOME := $(or $(ANDROID_HOME),$(ANDROID_SDK_ROOT),$(wildcard $(HOME)/Library/Android/sdk),$(wildcard $(HOME)/Android/Sdk),$(wildcard /usr/lib/android-sdk),$(wildcard /opt/android-sdk))

apk: ## Build the Android app and stage it for download at /api/setup/apk
	cd mobile && npx cap sync android
	cd mobile/android && JAVA_HOME="$(APK_JAVA_HOME)" ANDROID_HOME="$(APK_ANDROID_HOME)" ./gradlew assembleDebug
	cp mobile/android/app/build/outputs/apk/debug/app-debug.apk app/static/wemo-manager.apk
	@echo "Staged app/static/wemo-manager.apk"

logs: ## Tail the log file
	tail -f $(LOG_FILE)

deploy: ## Push this working tree to the Docker deployment and rebuild it
	./deploy.sh

deploy-start: ## Start the deployed Docker container (WEMO_MANAGER_DEPLOY_DIR, default ./wemo-manager-deploy)
	docker compose --project-directory $(DEPLOY_DIR) up -d

deploy-stop: ## Stop the deployed Docker container
	docker compose --project-directory $(DEPLOY_DIR) stop

deploy-restart: ## Restart the deployed Docker container
	docker compose --project-directory $(DEPLOY_DIR) restart

deploy-status: ## Show docker compose ps for the deployed container
	docker compose --project-directory $(DEPLOY_DIR) ps

deploy-logs: ## Tail logs from the deployed Docker container
	docker compose --project-directory $(DEPLOY_DIR) logs -f
