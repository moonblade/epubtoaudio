import os
from pathlib import Path

BASE_DIR = Path(__file__).parent

UPLOAD_PATH = Path(os.getenv("EPUBTOAUDIO_UPLOAD_PATH", str(BASE_DIR / "input")))
OUTPUT_PATH = Path(os.getenv("EPUBTOAUDIO_OUTPUT_PATH", str(BASE_DIR / "output")))

JOBS_PATH = BASE_DIR / "jobs"
MODELS_PATH = BASE_DIR / "models"
TEMPLATES_PATH = BASE_DIR / "templates"
STATIC_PATH = BASE_DIR / "static"
VOICE_MAPPINGS_PATH = BASE_DIR / "voice_mappings"

for path in [UPLOAD_PATH, OUTPUT_PATH, JOBS_PATH, MODELS_PATH, VOICE_MAPPINGS_PATH]:
    path.mkdir(parents=True, exist_ok=True)

MODEL_FILE = MODELS_PATH / "kokoro-v1.0.onnx"
VOICES_FILE = MODELS_PATH / "voices-v1.0.bin"

MODEL_URL = "https://github.com/nazdridoy/kokoro-tts/releases/download/v1.0.0/kokoro-v1.0.onnx"
VOICES_URL = "https://github.com/nazdridoy/kokoro-tts/releases/download/v1.0.0/voices-v1.0.bin"

DEFAULT_VOICE = "am_adam"
