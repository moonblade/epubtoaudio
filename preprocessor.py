#!/usr/bin/env python3.12
"""
Expressive preprocessing for EPUB to audiobook conversion.

Handles scene breaks, dialogue/thought detection, speaker attribution,
and prosody control based on ACX/Audible production standards.
"""

import re
import tempfile
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional
from bs4 import BeautifulSoup, Tag


class SegmentType(str, Enum):
    NARRATION = "narration"
    DIALOGUE = "dialogue"
    THOUGHT = "thought"
    SCENE_BREAK = "scene_break"
    CHAPTER_START = "chapter_start"


@dataclass
class TextSegment:
    text: str
    segment_type: SegmentType
    speaker: Optional[str] = None
    pause_before_seconds: float = 0.0
    pause_after_seconds: float = 0.0
    speed: float = 1.0
    voice_override: Optional[str] = None


@dataclass
class ProcessedChapter:
    title: str
    order: int
    segments: list[TextSegment] = field(default_factory=list)


PAUSE_SECONDS = {
    "sentence": 0.7,
    "paragraph": 1.5,
    "section_break": 2.7,
    "chapter_boundary": 3.5,
    "dialogue_start": 0.3,
    "dialogue_end": 0.4,
    "thought_start": 0.5,
    "thought_end": 0.5,
}

SPEED_BY_SEGMENT_TYPE = {
    SegmentType.NARRATION: 1.0,
    SegmentType.DIALOGUE: 1.05,
    SegmentType.THOUGHT: 0.92,
    SegmentType.SCENE_BREAK: 1.0,
    SegmentType.CHAPTER_START: 0.95,
}

SCENE_BREAK_PATTERNS = [
    r'^\s*[\*]{3,}\s*$',
    r'^\s*[-]{3,}\s*$',
    r'^\s*[#]{3,}\s*$',
    r'^\s*[~]{3,}\s*$',
    r'^\s*[\*\s]+[\*]+\s*$',
    r'^\s*[-\s]+[-]+\s*$',
    r'^\s*[•]{3,}\s*$',
]

SPEECH_VERBS = [
    "said", "says", "asked", "replied", "answered", "whispered", "shouted",
    "yelled", "screamed", "muttered", "murmured", "growled", "snapped",
    "barked", "hissed", "sighed", "groaned", "moaned", "laughed", "cried",
    "exclaimed", "declared", "announced", "stated", "added", "continued",
    "began", "started", "finished", "concluded", "interrupted", "demanded",
    "questioned", "wondered", "thought", "mused", "pondered", "considered",
    "called", "spoke", "told", "repeated", "echoed",
]

VOICE_PROFILES = {
    "af_alloy": {"gender": "female", "accent": "us"},
    "af_aoede": {"gender": "female", "accent": "us"},
    "af_bella": {"gender": "female", "accent": "us"},
    "af_heart": {"gender": "female", "accent": "us"},
    "af_jessica": {"gender": "female", "accent": "us"},
    "af_kore": {"gender": "female", "accent": "us"},
    "af_nicole": {"gender": "female", "accent": "us"},
    "af_nova": {"gender": "female", "accent": "us"},
    "af_river": {"gender": "female", "accent": "us"},
    "af_sarah": {"gender": "female", "accent": "us"},
    "af_sky": {"gender": "female", "accent": "us"},
    "am_adam": {"gender": "male", "accent": "us"},
    "am_echo": {"gender": "male", "accent": "us"},
    "am_eric": {"gender": "male", "accent": "us"},
    "am_fenrir": {"gender": "male", "accent": "us"},
    "am_liam": {"gender": "male", "accent": "us"},
    "am_michael": {"gender": "male", "accent": "us"},
    "am_onyx": {"gender": "male", "accent": "us"},
    "am_puck": {"gender": "male", "accent": "us"},
    "bf_alice": {"gender": "female", "accent": "uk"},
    "bf_emma": {"gender": "female", "accent": "uk"},
    "bf_isabella": {"gender": "female", "accent": "uk"},
    "bf_lily": {"gender": "female", "accent": "uk"},
    "bm_daniel": {"gender": "male", "accent": "uk"},
    "bm_fable": {"gender": "male", "accent": "uk"},
    "bm_george": {"gender": "male", "accent": "uk"},
    "bm_lewis": {"gender": "male", "accent": "uk"},
}

FEMALE_NAMES = frozenset([
    "alice", "anna", "bella", "claire", "diana", "emma", "fiona", "grace",
    "hannah", "isabella", "jessica", "kate", "laura", "mary", "nancy", "olivia",
    "patricia", "quinn", "rachel", "sarah", "tina", "uma", "victoria", "wendy",
    "elizabeth", "catherine", "margaret", "helen", "jane", "sophie", "emily",
    "charlotte", "ella", "mia", "lily", "rose",
])

MALE_NAMES = frozenset([
    "adam", "bob", "charles", "david", "edward", "frank", "george", "henry",
    "ian", "jack", "kevin", "liam", "michael", "nathan", "oliver", "peter",
    "robert", "samuel", "thomas", "victor", "william", "james", "john", "richard",
    "daniel", "matthew", "christopher", "andrew", "joseph", "paul", "mark",
    "steven", "eric", "brian", "jason",
])

FEMALE_TITLES = frozenset(["mrs", "ms", "miss", "lady", "queen", "princess", "mother", "sister", "aunt"])
MALE_TITLES = frozenset(["mr", "sir", "lord", "king", "prince", "father", "brother", "uncle"])

PRONOUNS = frozenset([
    "he", "she", "they", "it", "i", "we", "you",
    "him", "her", "them", "me", "us",
    "his", "hers", "theirs", "its", "my", "our", "your",
    "himself", "herself", "themselves", "itself", "myself", "ourselves", "yourself",
])


class SpeakerTracker:
    def __init__(self, narrator_voice: str = "am_adam", accent: str = "us",
                 initial_speakers: Optional[dict[str, str]] = None,
                 initial_genders: Optional[dict[str, str]] = None,
                 initial_used_voices: Optional[set[str]] = None):
        self.narrator_voice = narrator_voice
        self.accent = accent
        self.speaker_voices: dict[str, str] = {"NARRATOR": narrator_voice}
        self.speaker_genders: dict[str, str] = {}
        self._voice_pools = self._build_voice_pools()
        self._assigned_voices: set[str] = {narrator_voice}
        
        if initial_speakers:
            self.speaker_voices.update(initial_speakers)
        if initial_genders:
            self.speaker_genders.update(initial_genders)
        if initial_used_voices:
            self._assigned_voices.update(initial_used_voices)

    def _build_voice_pools(self) -> dict[str, list[str]]:
        pools: dict[str, list[str]] = {
            "female_us": [], "female_uk": [],
            "male_us": [], "male_uk": [],
        }
        for voice_id, profile in VOICE_PROFILES.items():
            key = f"{profile['gender']}_{profile['accent']}"
            pools[key].append(voice_id)
        return pools

    def _normalize_name(self, speaker: str) -> str:
        normalized = speaker.strip().title()
        return re.sub(r"[''']s?$", "", normalized)

    def _infer_gender(self, speaker: str) -> str:
        first_name = speaker.lower().split()[0] if speaker else ""
        
        if first_name in FEMALE_NAMES:
            return "female"
        if first_name in MALE_NAMES:
            return "male"
        
        speaker_lower = speaker.lower()
        if any(title in speaker_lower for title in FEMALE_TITLES):
            return "female"
        if any(title in speaker_lower for title in MALE_TITLES):
            return "male"
        
        return "unknown"

    def get_voice(self, speaker: Optional[str]) -> str:
        if speaker is None or speaker.upper() == "NARRATOR":
            return self.narrator_voice

        normalized = self._normalize_name(speaker)

        if normalized in self.speaker_voices:
            return self.speaker_voices[normalized]

        gender = self._infer_gender(normalized)
        self.speaker_genders[normalized] = gender

        if gender == "unknown":
            gender = "female" if len(self.speaker_voices) % 2 == 0 else "male"

        pool_key = f"{gender}_{self.accent}"
        pool = self._voice_pools.get(pool_key, [])

        for voice in pool:
            if voice not in self._assigned_voices:
                self.speaker_voices[normalized] = voice
                self._assigned_voices.add(voice)
                return voice

        voice = pool[len(self.speaker_voices) % len(pool)] if pool else self.narrator_voice
        self.speaker_voices[normalized] = voice
        return voice

    def register_speaker_gender(self, speaker: str, gender: str) -> None:
        normalized = self._normalize_name(speaker)
        self.speaker_genders[normalized] = gender

    def get_all_speakers(self) -> dict[str, str]:
        return dict(self.speaker_voices)


class BookNLPSpeakerDetector:
    """
    High-accuracy speaker detection using BookNLP.
    
    BookNLP provides 86-90% accuracy on speaker attribution by using
    BERT-based models trained on literary texts. Falls back to regex
    patterns if BookNLP is not installed.
    """
    
    def __init__(self):
        self._booknlp = None
        self._available = self._check_availability()
    
    def _check_availability(self) -> bool:
        try:
            from booknlp.booknlp import BookNLP
            self._booknlp_class = BookNLP
            return True
        except ImportError:
            return False
    
    @property
    def is_available(self) -> bool:
        return self._available
    
    def _initialize_model(self) -> None:
        if self._booknlp is None and self._available:
            self._booknlp = self._booknlp_class(
                "en",
                {"pipeline": "entity,quote,coref", "model": "small"}
            )
    
    def extract_speaker_attributions(self, text: str) -> dict[tuple[int, int], str]:
        """
        Extract speaker attributions for all quotes in text.
        
        Returns dict mapping (quote_start, quote_end) -> speaker_name
        """
        if not self._available:
            return {}
        
        self._initialize_model()
        
        if self._booknlp is None:
            return {}
        
        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = Path(tmpdir) / "input.txt"
            output_path = Path(tmpdir) / "output"
            input_path.write_text(text)
            
            self._booknlp.process(str(input_path), str(output_path), "text")
            
            quotes_file = output_path / "text.quotes"
            if not quotes_file.exists():
                return {}
            
            attributions = {}
            entities_file = output_path / "text.entities"
            entity_names = self._load_entity_names(entities_file)
            
            for line in quotes_file.read_text().strip().split("\n"):
                if not line:
                    continue
                parts = line.split("\t")
                if len(parts) >= 5:
                    quote_start = int(parts[0])
                    quote_end = int(parts[1])
                    speaker_id = parts[4]
                    if speaker_id in entity_names:
                        attributions[(quote_start, quote_end)] = entity_names[speaker_id]
            
            return attributions
    
    def _load_entity_names(self, entities_file: Path) -> dict[str, str]:
        if not entities_file.exists():
            return {}
        
        names = {}
        for line in entities_file.read_text().strip().split("\n"):
            if not line:
                continue
            parts = line.split("\t")
            if len(parts) >= 3:
                entity_id = parts[0]
                entity_name = parts[2]
                names[entity_id] = entity_name
        
        return names


class ExpressivePreprocessor:
    def __init__(
        self,
        narrator_voice: str = "am_adam",
        enable_speaker_detection: bool = True,
        enable_multi_voice: bool = True,
        use_booknlp: bool = True,
        book_slug: Optional[str] = None,
    ):
        self.narrator_voice = narrator_voice
        self.enable_speaker_detection = enable_speaker_detection
        self.enable_multi_voice = enable_multi_voice
        self.book_slug = book_slug

        accent = "uk" if narrator_voice.startswith("b") else "us"
        
        initial_speakers = None
        initial_genders = None
        initial_used_voices = None
        
        if book_slug:
            from voice_mapping_store import VoiceMappingStore
            self._voice_store = VoiceMappingStore()
            saved = self._voice_store.load(book_slug)
            if saved["speakers"]:
                initial_speakers = saved["speakers"]
                initial_genders = saved["genders"]
                initial_used_voices = saved["used_voices"]
                if saved["narrator_voice"]:
                    self.narrator_voice = saved["narrator_voice"]
        else:
            self._voice_store = None
        
        self.speaker_tracker = SpeakerTracker(
            self.narrator_voice, accent,
            initial_speakers, initial_genders, initial_used_voices
        )

        self._scene_break_pattern = re.compile("|".join(SCENE_BREAK_PATTERNS), re.MULTILINE)
        self._speaker_attribution_pattern = self._compile_speaker_pattern()
        
        self._booknlp_detector: Optional[BookNLPSpeakerDetector] = None
        if use_booknlp:
            detector = BookNLPSpeakerDetector()
            if detector.is_available:
                self._booknlp_detector = detector
    
    def save_voice_mappings(self) -> None:
        if self._voice_store and self.book_slug:
            self._voice_store.save(
                self.book_slug,
                self.speaker_tracker.speaker_voices,
                self.speaker_tracker.speaker_genders,
                self.narrator_voice,
                self.speaker_tracker._assigned_voices,
            )

    def _compile_speaker_pattern(self) -> re.Pattern:
        verbs = "|".join(SPEECH_VERBS)
        patterns = [
            rf'(?P<speaker1>[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s+(?:{verbs})',
            rf'(?:{verbs})\s+(?P<speaker2>[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)',
        ]
        return re.compile("|".join(patterns), re.IGNORECASE)

    def _is_scene_break(self, text: str) -> bool:
        return bool(self._scene_break_pattern.match(text.strip()))

    def _extract_speaker_regex(self, context: str) -> Optional[str]:
        if not self.enable_speaker_detection:
            return None
        match = self._speaker_attribution_pattern.search(context)
        if match:
            speaker = match.group("speaker1") or match.group("speaker2")
            if speaker and speaker.lower() not in PRONOUNS:
                return speaker
        return None

    def _extract_italicized_text(self, element: Tag) -> set[str]:
        return {tag.get_text().strip() for tag in element.find_all(["i", "em"])}

    def _create_narration_segment(self, text: str, pause_after: float = 0.0) -> TextSegment:
        return TextSegment(
            text=text,
            segment_type=SegmentType.NARRATION,
            pause_after_seconds=pause_after or PAUSE_SECONDS["sentence"],
            speed=SPEED_BY_SEGMENT_TYPE[SegmentType.NARRATION],
        )

    def _create_thought_segment(self, text: str) -> TextSegment:
        return TextSegment(
            text=text,
            segment_type=SegmentType.THOUGHT,
            pause_before_seconds=PAUSE_SECONDS["thought_start"],
            pause_after_seconds=PAUSE_SECONDS["thought_end"],
            speed=SPEED_BY_SEGMENT_TYPE[SegmentType.THOUGHT],
        )

    def _create_dialogue_segment(self, text: str, speaker: Optional[str], voice: Optional[str]) -> TextSegment:
        return TextSegment(
            text=text,
            segment_type=SegmentType.DIALOGUE,
            speaker=speaker,
            pause_before_seconds=PAUSE_SECONDS["dialogue_start"],
            pause_after_seconds=PAUSE_SECONDS["dialogue_end"],
            speed=SPEED_BY_SEGMENT_TYPE[SegmentType.DIALOGUE],
            voice_override=voice,
        )

    def _split_by_thoughts(self, text: str, thought_texts: set[str]) -> list[TextSegment]:
        if not thought_texts or not text:
            return [self._create_narration_segment(text)] if text else []

        segments: list[TextSegment] = []
        remaining = text

        for thought in thought_texts:
            if thought not in remaining:
                continue
            
            before, _, after = remaining.partition(thought)
            
            if before.strip():
                segments.append(self._create_narration_segment(before.strip(), pause_after=0.0))
            
            segments.append(self._create_thought_segment(thought))
            remaining = after

        if remaining.strip():
            segments.append(self._create_narration_segment(remaining.strip()))

        return segments

    def _parse_paragraph(self, element: Tag, booknlp_attributions: Optional[dict] = None) -> list[TextSegment]:
        full_text = element.get_text()

        if self._is_scene_break(full_text):
            return [TextSegment(
                text="",
                segment_type=SegmentType.SCENE_BREAK,
                pause_before_seconds=PAUSE_SECONDS["section_break"],
            )]

        thought_texts = self._extract_italicized_text(element)
        segments: list[TextSegment] = []

        dialogue_pattern = r'[\u0022\u201c\u201d\u00ab\u00bb]([^\u0022\u201c\u201d\u00ab\u00bb]+)[\u0022\u201c\u201d\u00ab\u00bb]'
        last_end = 0

        for match in re.finditer(dialogue_pattern, full_text):
            start, end = match.span()
            dialogue_text = match.group(1).strip()

            if start > last_end:
                narration = full_text[last_end:start].strip()
                if narration:
                    segments.extend(self._split_by_thoughts(narration, thought_texts))

            speaker = None
            if booknlp_attributions and (start, end) in booknlp_attributions:
                speaker = booknlp_attributions[(start, end)]
            else:
                context_window = full_text[max(0, start - 100):min(len(full_text), end + 100)]
                speaker = self._extract_speaker_regex(context_window)

            voice = None
            if self.enable_multi_voice and speaker:
                voice = self.speaker_tracker.get_voice(speaker)

            segments.append(self._create_dialogue_segment(dialogue_text, speaker, voice))
            last_end = end

        if last_end < len(full_text):
            remaining = full_text[last_end:].strip()
            if remaining:
                segments.extend(self._split_by_thoughts(remaining, thought_texts))

        if not segments:
            segments = self._split_by_thoughts(full_text.strip(), thought_texts)

        return segments

    def process_chapter_html(self, html_content: bytes, title: str, order: int) -> ProcessedChapter:
        soup = BeautifulSoup(html_content, "html.parser")
        chapter = ProcessedChapter(title=title, order=order)

        chapter.segments.append(TextSegment(
            text=title,
            segment_type=SegmentType.CHAPTER_START,
            pause_before_seconds=PAUSE_SECONDS["chapter_boundary"],
            pause_after_seconds=PAUSE_SECONDS["chapter_boundary"],
            speed=SPEED_BY_SEGMENT_TYPE[SegmentType.CHAPTER_START],
        ))

        full_chapter_text = soup.get_text()
        booknlp_attributions = None
        if self._booknlp_detector:
            booknlp_attributions = self._booknlp_detector.extract_speaker_attributions(full_chapter_text)

        block_elements = soup.find_all(["p", "div", "blockquote", "h1", "h2", "h3", "h4", "h5", "h6"])
        previous_was_scene_break = False

        for element in block_elements:
            text = element.get_text().strip()
            if not text or (len(text) < 10 and element.name in ("div", "p")):
                continue

            element_segments = self._parse_paragraph(element, booknlp_attributions)

            for seg in element_segments:
                if seg.segment_type == SegmentType.SCENE_BREAK:
                    if previous_was_scene_break:
                        continue
                    previous_was_scene_break = True
                else:
                    if chapter.segments and chapter.segments[-1].segment_type != SegmentType.SCENE_BREAK:
                        seg.pause_before_seconds = max(seg.pause_before_seconds, PAUSE_SECONDS["paragraph"])
                    previous_was_scene_break = False

                chapter.segments.append(seg)

        return chapter

    def chunk_segments(self, segments: list[TextSegment], max_chars: int = 1000) -> list[list[TextSegment]]:
        chunks: list[list[TextSegment]] = []
        current_chunk: list[TextSegment] = []
        current_size = 0

        for segment in segments:
            if segment.segment_type in (SegmentType.SCENE_BREAK, SegmentType.CHAPTER_START):
                if current_chunk:
                    chunks.append(current_chunk)
                    current_chunk = []
                    current_size = 0
                chunks.append([segment])
                continue

            seg_size = len(segment.text)

            if current_size + seg_size > max_chars and current_chunk:
                chunks.append(current_chunk)
                current_chunk = []
                current_size = 0

            if seg_size > max_chars:
                for sentence in self._split_into_sentences(segment.text):
                    if len(sentence) > max_chars:
                        for word_chunk in self._split_by_words(sentence, max_chars):
                            chunks.append([TextSegment(
                                text=word_chunk,
                                segment_type=segment.segment_type,
                                speaker=segment.speaker,
                                speed=segment.speed,
                                voice_override=segment.voice_override,
                            )])
                    else:
                        if current_size + len(sentence) > max_chars and current_chunk:
                            chunks.append(current_chunk)
                            current_chunk = []
                            current_size = 0
                        current_chunk.append(TextSegment(
                            text=sentence,
                            segment_type=segment.segment_type,
                            speaker=segment.speaker,
                            speed=segment.speed,
                            voice_override=segment.voice_override,
                        ))
                        current_size += len(sentence)
            else:
                current_chunk.append(segment)
                current_size += seg_size

        if current_chunk:
            chunks.append(current_chunk)

        return chunks

    def _split_into_sentences(self, text: str) -> list[str]:
        return [s.strip() for s in re.split(r'(?<=[.!?])\s+', text) if s.strip()]

    def _split_by_words(self, text: str, max_chars: int) -> list[str]:
        words = text.split()
        pieces: list[str] = []
        current_piece: list[str] = []
        current_len = 0

        for word in words:
            word_len = len(word) + 1
            if current_len + word_len > max_chars and current_piece:
                pieces.append(" ".join(current_piece))
                current_piece = []
                current_len = 0
            current_piece.append(word)
            current_len += word_len

        if current_piece:
            pieces.append(" ".join(current_piece))

        return pieces

    def get_speaker_voice_map(self) -> dict[str, str]:
        return self.speaker_tracker.get_all_speakers()
    
    @property
    def using_booknlp(self) -> bool:
        return self._booknlp_detector is not None


def generate_silence_samples(duration_seconds: float, sample_rate: int = 24000) -> list[float]:
    return [0.0] * int(duration_seconds * sample_rate)
