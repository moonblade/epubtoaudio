# EPUB to Audiobook Converter

> **AI-powered EPUB to audiobook converter with expressive multi-voice narration**

Convert your EPUB ebooks into natural-sounding audiobooks with automatic speaker detection, multi-voice dialogue, and professional-grade prosody. Powered by [Kokoro TTS](https://github.com/nazdridoy/kokoro-tts).

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-green.svg)](https://fastapi.tiangolo.com/)

---

## Why This Project?

Most EPUB-to-audio tools produce monotonous, robotic narration. This converter creates **audiobooks that feel professionally narrated**:

- **Different voices for different characters** - "Hello," said John. "Hi," replied Mary. → Different voices automatically
- **Natural pauses** - Scene breaks, chapter transitions, and dialogue get appropriate silence
- **Expressive delivery** - Dialogue is slightly faster, internal thoughts are slower and contemplative
- **Consistent characters** - The same character keeps the same voice across all chapters

---

## Features

### Core Conversion
- **EPUB to MP3** - Chapter-by-chapter audiobook output
- **27 English voices** - US and UK accents, male and female
- **Web interface** - Drag-and-drop upload, real-time progress
- **Stop/Resume** - Pause conversions and continue later
- **REST API** - Full programmatic control

### Expressive Narration (NEW)
- **Multi-voice dialogue** - Each speaker gets a unique, consistent voice
- **Speaker detection** - Automatic attribution via speech patterns ("said John")
- **Thought detection** - Italicized text rendered with introspective cadence
- **Scene breaks** - Automatic detection of `***`, `---`, `###` markers
- **ACX/Audible timing** - Professional pause durations at every level

### Prosody Control
| Content Type | Speed | Pause After |
|-------------|-------|-------------|
| Narration | 1.0x | 0.3s |
| Dialogue | 1.05x | 0.2s |
| Internal thoughts | 0.92x | 0.25s |
| Chapter start | 0.95x | 1.5s |
| Scene break | — | 1.2s |
| Paragraph | — | 0.6s |

---

## Quick Start

```bash
# Clone the repository
git clone https://github.com/moonblade/epub-to-audiobook.git
cd epub-to-audiobook

# Setup and run (models download automatically)
make run
```

Open **http://localhost:3002** in your browser.

That's it! Upload an EPUB, select a voice, and watch the conversion progress in real-time.

---

## Installation

### Requirements
- Python 3.12+
- ~500MB disk space (TTS models)
- macOS, Linux, or Windows (WSL)

### Option 1: Make (Recommended)

```bash
make setup    # Create venv, install deps, download models
make run      # Start the server on port 3002
```

### Option 2: Manual Installation

```bash
# Create virtual environment
python3.12 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Download TTS models (~500MB)
mkdir -p models
curl -L -o models/kokoro-v1.0.onnx \
  https://github.com/nazdridoy/kokoro-tts/releases/download/v1.0.0/kokoro-v1.0.onnx
curl -L -o models/voices-v1.0.bin \
  https://github.com/nazdridoy/kokoro-tts/releases/download/v1.0.0/voices-v1.0.bin

# Run the server
uvicorn main:app --host 0.0.0.0 --port 3002
```

### Option 3: Docker

```bash
docker run -d \
  --name epubtoaudio \
  -p 3002:3002 \
  -v ./input:/data/input \
  -v ./output:/data/output \
  ghcr.io/moonblade/epubtoaudio:latest
```

Or with docker-compose:

```yaml
services:
  epubtoaudio:
    image: ghcr.io/moonblade/epubtoaudio:latest
    ports:
      - "3002:3002"
    volumes:
      - ./input:/data/input
      - ./output:/data/output
    restart: unless-stopped
```

The Docker image includes:
- Python 3.12 with all dependencies
- TTS models pre-downloaded (~500MB)
- spaCy English model
- ffmpeg for audio processing

---

## Usage

### Web Interface

1. Open http://localhost:3002
2. Drag & drop your EPUB file (or click to browse)
3. Select a narrator voice from the dropdown
4. Click **Convert** and watch real-time progress
5. Download individual chapters or the full audiobook

### Command Line (via API)

```bash
# Upload and start conversion
curl -X POST http://localhost:3002/upload \
  -F "file=@mybook.epub" \
  -F "voice=af_bella"

# Check job status
curl http://localhost:3002/jobs/{job_id}

# Download chapter
curl -O http://localhost:3002/jobs/{job_id}/audio/1
```

### Python Integration

```python
import requests

# Upload EPUB
with open("mybook.epub", "rb") as f:
    response = requests.post(
        "http://localhost:3002/upload",
        files={"file": f},
        data={"voice": "am_adam"}
    )
job_id = response.json()["job_id"]

# Poll for completion
while True:
    status = requests.get(f"http://localhost:3002/jobs/{job_id}").json()
    if status["status"] == "completed":
        break
    time.sleep(5)

# Download audio
audio = requests.get(f"http://localhost:3002/jobs/{job_id}/audio/1")
```

---

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `EPUBTOAUDIO_UPLOAD_PATH` | `./input` | Directory for uploaded EPUB files |
| `EPUBTOAUDIO_OUTPUT_PATH` | `./output` | Directory for generated audio files |

```bash
# Custom paths
EPUBTOAUDIO_UPLOAD_PATH=/data/books \
EPUBTOAUDIO_OUTPUT_PATH=/data/audiobooks \
make run
```

### Logs

Logs are stored in `~/Library/Logs/epubtoaudio/` with daily rotation.

```bash
# Tail the logs
make logs
```

---

## Available Voices

### US English

| Male | Female |
|------|--------|
| am_adam *(default)* | af_alloy |
| am_echo | af_aoede |
| am_eric | af_bella |
| am_fenrir | af_heart |
| am_liam | af_jessica |
| am_michael | af_kore |
| am_onyx | af_nicole |
| am_puck | af_nova |
| | af_river |
| | af_sarah |
| | af_sky |

### UK English

| Male | Female |
|------|--------|
| bm_daniel | bf_alice |
| bm_fable | bf_emma |
| bm_george | bf_isabella |
| bm_lewis | bf_lily |

**Voice preview**: The web interface includes sample audio for each voice.

---

## API Reference

### Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/` | Web interface |
| `POST` | `/upload` | Upload EPUB and start conversion |
| `GET` | `/jobs` | List all conversion jobs |
| `GET` | `/jobs/{id}` | Get job status and progress |
| `POST` | `/jobs/{id}/stop` | Pause a running conversion |
| `POST` | `/jobs/{id}/resume` | Resume a paused conversion |
| `DELETE` | `/jobs/{id}` | Delete job and all associated files |
| `GET` | `/jobs/{id}/logs` | SSE stream of conversion logs |
| `GET` | `/jobs/{id}/audio/{chapter}` | Download specific chapter MP3 |
| `GET` | `/voices` | List all available voices |

### Upload Parameters

```
POST /upload
Content-Type: multipart/form-data

file: EPUB file (required)
voice: Voice ID (default: am_adam)
upload_path: Custom input directory (optional)
output_path: Custom output directory (optional)
```

### Response Models

```json
// Job Status
{
  "job_id": "a1b2c3d4",
  "status": "processing",  // pending, processing, completed, failed, paused
  "voice": "am_adam",
  "epub_filename": "mybook.epub",
  "progress": 45.2,
  "current_chapter": 5,
  "total_chapters": 12,
  "error": null,
  "created_at": "2024-01-15T10:30:00Z",
  "updated_at": "2024-01-15T10:35:00Z"
}
```

---

## Advanced Features

### Enhanced Speaker Detection (Optional)

For 86-90% speaker attribution accuracy, install BookNLP:

```bash
pip install booknlp>=1.0.7
```

BookNLP uses BERT-based coreference resolution to attribute dialogue more accurately. It runs on CPU (~1.5-3GB memory).

### Persistent Voice Mappings

Character voices are saved per book in `voice_mappings/`. When converting multiple chapters of the same book:

1. First chapter: Characters are detected and assigned voices
2. Subsequent chapters: Same characters automatically use the same voices

File naming convention: `YYYY-MM-DD - Book Title - Chapter N.epub`

---

## Project Structure

```
epub-to-audiobook/
├── main.py                 # FastAPI application & endpoints
├── converter.py            # EPUB parsing + TTS conversion engine
├── preprocessor.py         # Expressive preprocessing (NEW)
├── voice_mapping_store.py  # Persistent character-voice mappings (NEW)
├── job_manager.py          # Job state persistence
├── log_store.py            # Log persistence for SSE
├── models.py               # Pydantic models
├── config.py               # Configuration
├── logger.py               # Logging with daily rotation
├── templates/              # Jinja2 HTML templates
├── static/                 # CSS, favicon, voice samples
├── models/                 # TTS model files (gitignored)
├── input/                  # Uploaded EPUBs (gitignored)
├── output/                 # Generated audio (gitignored)
├── jobs/                   # Job state JSON (gitignored)
└── voice_mappings/         # Character voice assignments (gitignored)
```

---

## Troubleshooting

### "Models not found" error

```bash
make download-models
```

### Conversion is slow

- Each chapter takes ~1-3 minutes depending on length
- TTS runs on CPU; GPU acceleration coming soon
- Check `make logs` for progress

### Audio sounds robotic

- Enable expressive preprocessing (on by default)
- Try different voices - some are more natural than others
- `af_bella` and `am_adam` tend to sound best

### Characters not getting different voices

- Ensure dialogue uses standard quotes: `"Hello"` not `'Hello'`
- Speaker attribution works best with patterns like `"text," said John`
- Install BookNLP for better accuracy: `pip install booknlp`

---

## Roadmap

- [ ] Docker image
- [ ] GPU acceleration
- [ ] Batch processing
- [ ] Voice customization per character (manual override)
- [ ] Support for more ebook formats (MOBI, AZW3)
- [ ] Audio chapter markers (M4B format)

---

## Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/amazing-feature`
3. Make your changes
4. Run tests: `make test`
5. Submit a pull request

---

## License

MIT License - see [LICENSE](LICENSE) for details.

---

## Acknowledgments

- [Kokoro TTS](https://github.com/nazdridoy/kokoro-tts) - The incredible TTS engine
- [FastAPI](https://fastapi.tiangolo.com/) - Modern Python web framework
- [BookNLP](https://github.com/booknlp/booknlp) - Literary text processing (optional)

---

<p align="center">
  <b>Made with ❤️ for book lovers who want to listen</b>
</p>
