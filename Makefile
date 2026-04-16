.PHONY: setup run install clean download-models test lint logs samples test-ollama

PYTHON := python3.12
VENV := .venv
BIN := $(VENV)/bin
PORT := 3002
LOG_DIR := $(HOME)/Library/Logs/epubtoaudio

OLLAMA_HOST := https://ollama.sirius.moonblade.work
OLLAMA_MODEL := qwen2.5:0.5b

setup: $(VENV) install download-models

$(VENV):
	$(PYTHON) -m venv $(VENV)

install: $(VENV)
	$(BIN)/pip install --upgrade pip
	$(BIN)/pip install -r requirements.txt

download-models:
	@mkdir -p models
	@if [ ! -f models/kokoro-v1.0.onnx ]; then \
		echo "Downloading kokoro-v1.0.onnx (~300MB)..."; \
		curl -L -o models/kokoro-v1.0.onnx https://github.com/nazdridoy/kokoro-tts/releases/download/v1.0.0/kokoro-v1.0.onnx; \
	fi
	@if [ ! -f models/voices-v1.0.bin ]; then \
		echo "Downloading voices-v1.0.bin..."; \
		curl -L -o models/voices-v1.0.bin https://github.com/nazdridoy/kokoro-tts/releases/download/v1.0.0/voices-v1.0.bin; \
	fi
	@echo "Models ready."

run: setup
	$(BIN)/uvicorn main:app --reload --host 0.0.0.0 --port $(PORT)

samples: setup
	$(BIN)/python generate_samples.py

logs:
	@mkdir -p $(LOG_DIR)
	@if [ -f $(LOG_DIR)/epubtoaudio.log ]; then \
		tail -f $(LOG_DIR)/epubtoaudio.log; \
	else \
		echo "No log file yet. Start the server first with 'make run'"; \
	fi

test: $(VENV)
	$(BIN)/pytest tests/ -v

clean:
	rm -rf $(VENV)
	rm -rf __pycache__ */__pycache__
	rm -rf .pytest_cache
	rm -rf input/* output/* jobs/*
	find . -name "*.pyc" -delete

clean-all: clean
	rm -rf models/*.onnx models/*.bin
