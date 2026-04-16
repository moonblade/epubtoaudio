# Changelog

All notable changes to this project will be documented in this file.

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
