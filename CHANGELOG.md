# Changelog

All notable changes to this project will be documented in this file.

## [PR #8] - 2026-04-24 - Two-Phase Processing Pipeline & Debug Mode

Refactored the conversion pipeline to separate text preprocessing from TTS synthesis, enabling caching and debug workflows.

#### Architecture Changes
- **Two-phase pipeline**: Text preprocessing now completes entirely before TTS begins
- **Intermediate format**: Preprocessed chapters saved as `processed_book.json` with all segments, speaker mappings, and prosody data
- **Caching**: Subsequent runs skip preprocessing if `processed_book.json` exists

#### New Features
- **Preprocess-only mode**: `preprocess_only=True` parameter to run text processing without TTS
- **Debug workflow**: Inspect `processed_book.json` to verify preprocessing before committing to audio generation
- **ProcessedBook model**: New `ProcessedBook` and updated `ProcessedChapter` classes with `to_dict()`, `from_dict()`, `save()`, `load()` methods

#### API Changes
- `POST /upload`: Added `preprocess_only` form parameter (default: `false`)
- `POST /convert-from-browse`: Added `preprocess_only` form parameter (default: `false`)

#### Text Processing Fixes
- **Nested div duplication**: Skip parent `<div>` elements containing nested `<p>` elements (was causing content to be read twice)
- **Italics thought detection**: Use word boundaries to prevent matching "me" inside "measure"
- **Mid-sentence emphasis**: Only treat italics as thoughts when they start after punctuation AND end with punctuation
- **Ellipsis handling**: Increased pause from 0.3s to 0.6s, now splits text at ellipsis to insert pause at correct position
- **Roman numerals**: Convert Roman numerals (I-XX) to words after keywords like "tier", "level", "class" (e.g., "Tier III" → "Tier three")

#### CLI Tools
- **`pushepubaudio`**: New CLI script to upload generated MP3s to FileBrowser
  - Creates folder in `/downloads/epub-audio/` named after the audio files
  - Supports single file or directory of MP3s
  - Auto-detects common prefix for multi-file uploads

#### Files Changed
- `preprocessor.py`: Added `ProcessedBook` dataclass with serialization, text processing fixes
- `converter.py`: Split `run()` into `_preprocess_epub()` and `_synthesize_audio()` phases
- `main.py`: Added `preprocess_only` parameter to upload endpoints
- `pushepubaudio`: New CLI script for uploading audio to FileBrowser

## [PR #7] - 2026-04-17 - Audio Quality Enhancements & M4B Output

Major audio pipeline overhaul with normalization, prosody improvements, and M4B audiobook generation.

#### Audio Pipeline
- **LUFS normalization**: Two-pass ffmpeg loudnorm targeting -16 LUFS (ACX standard) per chapter
- **Segment crossfade**: 30ms fade-in/fade-out on every synthesized segment to eliminate hard cuts
- **Audio post-processing**: Gentle dynamic compression (3:1 ratio) + low-shelf EQ boost (120Hz) + presence boost (3kHz)
- **Volume boost for exclamations**: `!` segments get +15% gain, `!!`/`?!` get +25%, `?` gets +5%

#### Prosody Improvements
- **Paragraph pause fix**: Pause only applied to first segment of each `<p>`, not every segment (was causing 0.8s dead air between dialogue exchanges)
- **Punctuation-aware splitting**: Exclamatory sentences split at `!`/`?` boundaries with micro-pauses, but short segments (<4 words) are merged to avoid isolated utterances like "Why?" being synthesized alone
- **Attribution separation**: "Mordred said. He cleared his throat." → two segments with tight pacing
- **Speed variation**: Exclamations at 1.10x, double-exclamations at 1.13x, questions slightly slower at 1.02x

#### Text Normalization
- Numbers to words (`$500` → `five hundred dollars`, `3rd` → `3rd`)
- Abbreviations expanded (`Dr.` → `Doctor`, `etc.` → `etcetera`)
- **Stutter normalization**: `I..I` → `I-I` (hyphen form for natural TTS)
- **Interjection elongation**: `ah` → `ahh`, `oh` → `ohh`, `uh` → `uhh`, `hm` → `hmm` (prevents distorted short utterances)
- Sentence splitter made ellipsis-aware (won't split `"I think... Maybe"` at the dots)
- Symbols: `&` → `and`, `/` → `or`

#### Chapter Handling
- **Skip metadata chapters**: Chapters with <100 chars or <5 content blocks auto-skipped
- **Clean chapter titles**: Date prefix and book name stripped (`2026-04-16 - Book - Chapter 1: Title` → `Chapter 1: Title`)
- **Duplicate heading skip**: Heading elements matching the chapter title no longer read as narration
- **Speaker detection on by default**: Characters get distinct pitch shifts in dialogue

#### M4B Audiobook Output
- All chapter MP3s combined into a single `.m4b` file with chapter markers via ffmpeg
- New endpoint: `GET /jobs/{id}/audiobook` for M4B download
- M4B files included in final path copy

#### UI Improvements
- **Inline audio player**: Play/pause per chapter on the logs page with native browser controls
- **M4B download button**: "Download Full Audiobook (M4B)" at top of chapters section

#### Dev Workflow
- `make stop`: Kill process on PORT via lsof
- `EPUBTOAUDIO_BROWSE_PATH` set to `~/Downloads` for local `make run`

## [PR #6] - 2026-04-17 - Browse Files from Mounted Directory

Added ability to browse and convert EPUB files from a mounted directory instead of uploading.

#### New Features
- **Browse tab in UI**: Switch between Upload and Browse tabs
- **Directory navigation**: Navigate through folders to find EPUB files
- **Direct conversion**: Select files from browse and convert without uploading

#### New Endpoints
- `GET /browse?path=` - List EPUB files and directories at path
- `POST /convert-from-browse` - Start conversion from a browsed file path

#### Configuration
- **New env var**: `EPUBTOAUDIO_BROWSE_PATH` - Mount a directory for browsing (e.g., webtoepub output)

#### Files Changed
- `config.py`: Added `BROWSE_PATH` configuration
- `models.py`: Added `BrowseFile`, `BrowseResponse` models
- `main.py`: Added `/browse` and `/convert-from-browse` endpoints
- `templates/index.html`: Added tabbed UI with browse functionality

## [PR #6] - 2026-04-17 - Reduced Pause Timing & Preprocessing Debug API

Significantly reduced pause/silence durations and added a new `/preprocess` endpoint for debugging.

#### Pause Timing Changes (~50% reduction)
| Pause Type | Before | After |
|------------|--------|-------|
| Sentence | 0.7s | 0.3s |
| Paragraph | 1.5s | 0.6s |
| Section break | 2.7s | 1.2s |
| Chapter boundary | 3.5s | 1.5s |
| Dialogue start | 0.3s | 0.15s |
| Dialogue end | 0.4s | 0.2s |
| Thought start/end | 0.5s | 0.25s |

#### New `/preprocess` Endpoint
Debug endpoint to inspect preprocessing output before TTS conversion:
- `POST /preprocess` - Upload EPUB and get preprocessed segments as JSON
- Optional `chapter` query param to process a single chapter
- Returns: chapters with segments (text, type, speaker, pauses, speed, pitch)

#### Files Changed
- `preprocessor.py`: Updated `PAUSE_SECONDS` values
- `models.py`: Added `SegmentResponse`, `ChapterResponse`, `PreprocessResponse`
- `main.py`: Added `/preprocess` endpoint
- `README.md`: Updated prosody control table

## [PR #5] - 2026-04-17 - Final Output Path Configuration

Added option to copy completed audiobooks to a separate final output directory with the book name as the folder.

#### Changes
- **New env var**: `EPUBTOAUDIO_FINAL_PATH` - when set, completed MP3s are copied to this path
- **Book name folders**: MP3s are organized into folders named after the EPUB file (e.g., `My Book.epub` → `My Book/`)
- **Filename sanitization**: Invalid filesystem characters are removed from folder names
- **Overwrite behavior**: If folder already exists, it is replaced with the new conversion

#### Usage
```bash
EPUBTOAUDIO_FINAL_PATH=/audiobooks make run
```

This keeps the original job output in `OUTPUT_PATH` (for job management) while also providing a clean, organized copy in `FINAL_PATH`.

## [PR #4] - 2026-04-16 - Ollama Few-Shot Speaker Detection (93% Accuracy)

Improved Ollama speaker detection from ~40% to 93% accuracy using few-shot prompting:

#### Changes
- **Few-shot prompting**: Replaced instruction-based prompts with pattern-based few-shot examples
- **93% accuracy**: Manually verified against 43 test cases from 6 different EPUBs
- **Model upgrade**: Default model changed from `qwen2.5:0.5b` to `qwen2.5:1.5b` (986 MB)
- **Test suite**: Added comprehensive test suite with manually-crafted ground truth

#### Prompt Strategy
```
Who speaks? Return only the name.

"Hello" John said. → John
"Why?" Mary asked. → Mary

"<dialogue>" <context> →
```

#### Known Limitations (3 failure modes)
1. Pronoun resolution: "he said" requires broader context
2. Confusing phrasing: "Will directed Ria" can confuse extraction
3. No speaker in context: Dialogue without explicit attribution

#### Technical Changes
- Simplified `OllamaSpeakerDetector._build_prompt_*()` methods
- Increased timeout from 10s to 15s
- Added `test_ollama_extensive.py` with 43 manual test cases
- Parameters: `temperature: 0.0`, `num_predict: 10`

## [PR #3] - Dialogue Detection Foundation

Simplified speaker system to focus on dialogue detection without attribution:

#### Changes
- **Disabled speaker attribution**: Removed spaCy/Ollama/BookNLP speaker detection (accuracy was ~40% - not production ready)
- **Dialogue detection only**: Maintains accurate dialogue vs narration classification
- **Added spaCy/Ollama infrastructure**: Code ready for future speaker attribution improvements
- **Environment-based Ollama config**: `OLLAMA_HOST` and `OLLAMA_MODEL` env vars for external LLM

#### Technical Changes  
- Added `SpacySpeakerDetector` class (disabled by default)
- Added `OllamaSpeakerDetector` class (disabled by default)
- Defaults changed: `enable_speaker_detection=False`, `use_booknlp=False`
- Added `requests` and `spacy` to requirements.txt

## [PR #2] - Pitch-Based Speaker Differentiation

Replaced multi-voice speaker system with pitch-shift based differentiation for more consistent audio quality:

#### Changes
- **Single voice, multiple speakers**: All dialogue uses the narrator's voice with pitch variations
- **Pitch shifts by gender**: Female speakers get higher pitch (+1.5 to +3.0 semitones), male speakers get lower pitch (-1.0 to -2.5 semitones)
- **Consistent speaker identity**: Same character maintains same pitch shift across chapters
- **Improved audio consistency**: Eliminates speed variation issues between different TTS voices

#### Technical Changes
- Replaced `voice_override` with `pitch_shift` in TextSegment
- Added `pitch_shift_audio()` using scipy signal processing
- Updated `VoiceMappingStore` to persist pitch shifts instead of voice IDs
- Added scipy dependency for audio resampling

## [PR #1] - Expressive Audiobook Preprocessing

Major enhancement to produce more natural, expressive audiobook narration:

#### Speaker Detection & Multi-Voice Support
- Automatic speaker attribution using speech verb patterns ("said John", "Mary replied")
- Gender inference from character names for appropriate voice assignment
- Each detected speaker gets a unique, consistent voice throughout the book
- Optional BookNLP integration for 86-90% speaker attribution accuracy

#### Content-Aware Prosody
- **Dialogue**: 1.05x speed (slightly faster, more dynamic)
- **Internal thoughts** (italicized text): 0.92x speed (slower, introspective)
- **Chapter starts**: 0.95x speed (measured introduction)
- **Narration**: 1.0x speed (baseline)

#### Hierarchical Pause Timing (ACX/Audible standards)
- Sentence boundaries: 0.7s pause
- Paragraph breaks: 1.5s pause
- Scene breaks (`***`, `---`): 2.7s pause
- Chapter boundaries: 3.5s pause
- Dialogue transitions: 0.3-0.4s pause
- Thought transitions: 0.5s pause

#### Scene Break Detection
- Automatic detection of common scene break markers
- Patterns: `***`, `---`, `###`, `~~~`, `* * *`, `- - -`

### Technical Changes
- New `preprocessor.py` module with `ExpressivePreprocessor` class
- HTML structure preserved during EPUB parsing (italics, emphasis detection)
- Smart chunking that respects content boundaries
- Silence sample generation for pause insertion

### Optional Dependencies
- `booknlp>=1.0.7` - For enhanced speaker detection with coreference resolution

## [1.0.0] - Initial Release

### Features
- EPUB to MP3 audiobook conversion
- 27 English voices (US and UK accents)
- Web UI with drag-and-drop upload
- Real-time progress via SSE
- Stop/resume conversion support
- Chapter-wise output files
- Voice preview samples
