# Changelog

All notable changes to this project will be documented in this file.

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
