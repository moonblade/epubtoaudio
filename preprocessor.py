#!/usr/bin/env python3.12
import re
import tempfile
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

import numpy as np
import requests
import spacy
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
    pitch_shift: float = 0.0  # Semitones: positive=higher, negative=lower


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
    "mouthed", "breathed", "rasped", "croaked", "wheezed", "grunted",
    "quipped", "chimed", "interjected", "remarked", "noted", "observed",
    "suggested", "proposed", "offered", "admitted", "confessed",
    "protested", "objected", "agreed", "concurred", "countered",
    "retorted", "prompted", "urged", "pressed", "insisted", "maintained",
    "explained", "elaborated", "clarified", "specified",
    "chuckled", "giggled", "snickered", "sneered", "smirked", "grinned",
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

NON_SPEAKER_WORDS = frozenset([
    "more", "less", "much", "many", "some", "any", "all", "none", "most", "few",
    "something", "nothing", "everything", "anything", "someone", "anyone", "everyone",
    "somewhere", "anywhere", "everywhere", "nowhere",
    "now", "then", "here", "there", "where", "when", "how", "why", "what", "which",
    "yes", "no", "maybe", "perhaps", "probably", "certainly", "definitely",
    "just", "only", "even", "still", "already", "always", "never", "often", "sometimes",
    "very", "quite", "rather", "too", "enough", "almost", "nearly", "really", "actually",
    "again", "also", "anyway", "besides", "finally", "further", "however", "instead",
    "meanwhile", "moreover", "nevertheless", "otherwise", "therefore", "thus",
    "before", "after", "during", "while", "until", "since", "because", "although",
    "the", "a", "an", "this", "that", "these", "those",
])


PITCH_SHIFTS_FEMALE = [1.5, 2.5, 1.0, 3.0, 2.0]
PITCH_SHIFTS_MALE = [-1.0, -2.0, -1.5, -0.5, -2.5]

# Load spaCy model once at module level
try:
    _nlp = spacy.load("en_core_web_sm")
except OSError:
    _nlp = None


class SpeakerTracker:
    def __init__(
        self,
        initial_pitch_shifts: Optional[dict[str, float]] = None,
        initial_genders: Optional[dict[str, str]] = None,
    ):
        self.speaker_pitch_shifts: dict[str, float] = {"NARRATOR": 0.0}
        self.speaker_genders: dict[str, str] = {}
        self._female_index = 0
        self._male_index = 0
        
        if initial_pitch_shifts:
            self.speaker_pitch_shifts.update(initial_pitch_shifts)
            self._female_index = sum(1 for p in initial_pitch_shifts.values() if p > 0)
            self._male_index = sum(1 for p in initial_pitch_shifts.values() if p < 0)
        if initial_genders:
            self.speaker_genders.update(initial_genders)

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

    def get_pitch_shift(self, speaker: Optional[str]) -> float:
        if speaker is None or speaker.upper() == "NARRATOR":
            return 0.0

        normalized = self._normalize_name(speaker)

        if normalized in self.speaker_pitch_shifts:
            return self.speaker_pitch_shifts[normalized]

        gender = self._infer_gender(normalized)
        self.speaker_genders[normalized] = gender

        if gender == "unknown":
            gender = "female" if len(self.speaker_pitch_shifts) % 2 == 0 else "male"

        if gender == "female":
            pitch = PITCH_SHIFTS_FEMALE[self._female_index % len(PITCH_SHIFTS_FEMALE)]
            self._female_index += 1
        else:
            pitch = PITCH_SHIFTS_MALE[self._male_index % len(PITCH_SHIFTS_MALE)]
            self._male_index += 1

        self.speaker_pitch_shifts[normalized] = pitch
        return pitch

    def get_all_speakers(self) -> dict[str, float]:
        return dict(self.speaker_pitch_shifts)


class SpacySpeakerDetector:
    """
    Speaker detection using spaCy dependency parsing.
    
    Looks both BEFORE and AFTER dialogue for attribution patterns like:
    - "Hello," said Jason.  (verb AFTER dialogue)
    - Jason said, "Hello."  (verb BEFORE dialogue)
    
    Also resolves pronouns to the most recent proper noun subject.
    """
    
    def __init__(self):
        self._nlp = _nlp
        self._available = _nlp is not None
        self._recent_subjects: list[str] = []
    
    @property
    def is_available(self) -> bool:
        return self._available
    
    def reset_context(self) -> None:
        self._recent_subjects = []
    
    def _is_valid_speaker(self, text: str) -> bool:
        if not text or len(text) < 2:
            return False
        text_lower = text.lower()
        if text_lower in PRONOUNS or text_lower in NON_SPEAKER_WORDS:
            return False
        if len(text) == 1:
            return False
        if not text[0].isupper():
            return False
        return True
    
    def find_speaker(self, context_before: str, context_after: str) -> tuple[Optional[str], str]:
        if not self._available:
            return None, "spacy_unavailable"
        
        truncated_after = self._truncate_before_next_quote(context_after)
        
        speaker_after, method_after = self._find_speaker_in_context(truncated_after, is_after=True)
        if speaker_after and self._is_valid_speaker(speaker_after) and method_after in ("direct", "pronoun"):
            self._update_recent_subjects(speaker_after)
            return speaker_after, method_after
        
        speaker_before, method_before = self._find_speaker_in_context(context_before, is_after=False)
        if speaker_before and self._is_valid_speaker(speaker_before) and method_before in ("direct", "pronoun"):
            self._update_recent_subjects(speaker_before)
            return speaker_before, method_before
        
        return None, "none"
    
    def _truncate_before_next_quote(self, text: str) -> str:
        quote_chars = '"\u201c\u201d\u00ab\u00bb'
        for i, char in enumerate(text):
            if char in quote_chars:
                return text[:i]
        return text
    
    def _find_speaker_in_context(self, context: str, is_after: bool) -> tuple[Optional[str], str]:
        if not context.strip() or self._nlp is None:
            return None, "empty"
        
        doc = self._nlp(context)
        
        for token in doc:
            if token.lemma_.lower() in SPEECH_VERBS or token.text.lower() in SPEECH_VERBS:
                for child in token.children:
                    if child.dep_ == "nsubj":
                        if child.pos_ == "PROPN":
                            return child.text, "direct"
                        elif child.pos_ == "PRON":
                            resolved = self._resolve_pronoun(child.text, doc)
                            if resolved:
                                return resolved, f"pronoun:{child.text}"
        
        for token in doc:
            if token.pos_ == "PROPN" and token.dep_ in ("nsubj", "ROOT"):
                if self._is_valid_speaker(token.text):
                    return token.text, "propn_subject"
        
        return None, "none"
    
    def _resolve_pronoun(self, pronoun: str, doc) -> Optional[str]:
        pronoun_lower = pronoun.lower()
        
        for token in doc:
            if token.pos_ == "PROPN" and token.dep_ == "nsubj":
                if self._is_valid_speaker(token.text):
                    return token.text
        
        if self._recent_subjects:
            return self._recent_subjects[-1]
        
        return None
    
    def _update_recent_subjects(self, speaker: str) -> None:
        if speaker not in self._recent_subjects:
            self._recent_subjects.append(speaker)
        if len(self._recent_subjects) > 10:
            self._recent_subjects.pop(0)


class OllamaSpeakerDetector:
    """
    Speaker detection using local Ollama LLM.
    
    Uses a small language model (qwen2.5:0.5b) to reason about dialogue attribution,
    especially in rapid back-and-forth exchanges where regex/spaCy fail.
    
    Key advantage: Can understand conversational turn-taking:
        "Line 1," said Jason.
        "Line 2"  <- LLM can infer this is likely Jason continuing or a response
        "Line 3," Mary replied.
    
    Environment variables:
        OLLAMA_HOST: Ollama server URL (default: http://localhost:11434)
        OLLAMA_MODEL: Model name (default: qwen2.5:0.5b)
    """
    
    TIMEOUT_SECONDS = 10
    
    def __init__(self):
        import os
        self._host = os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
        self._model = os.environ.get("OLLAMA_MODEL", "qwen2.5:0.5b")
        self._available = self._check_availability()
        self._known_speakers: list[str] = []
    
    def _check_availability(self) -> bool:
        try:
            response = requests.get(
                f"{self._host}/api/tags",
                timeout=3
            )
            if response.status_code == 200:
                models = response.json().get("models", [])
                model_base = self._model.split(":")[0]
                return any(m.get("name", "").startswith(model_base) for m in models)
        except (requests.RequestException, ValueError):
            pass
        return False
    
    @property
    def is_available(self) -> bool:
        return self._available
    
    def reset_context(self) -> None:
        """Reset known speakers for a new chapter."""
        self._known_speakers = []
    
    def add_known_speaker(self, speaker: str) -> None:
        """Add a speaker discovered by other methods."""
        if speaker and speaker not in self._known_speakers:
            self._known_speakers.append(speaker)
    
    def _build_prompt(self, dialogue: str, context_before: str, context_after: str) -> str:
        """Build a focused prompt for speaker identification."""
        known_speakers_str = ", ".join(self._known_speakers) if self._known_speakers else "none yet"
        
        return f"""Identify who speaks the DIALOGUE below. Use ONLY the context provided.

CONTEXT BEFORE:
{context_before.strip() if context_before.strip() else "(none)"}

DIALOGUE: "{dialogue}"

CONTEXT AFTER:
{context_after.strip() if context_after.strip() else "(none)"}

Known speakers in this chapter: {known_speakers_str}

Rules:
1. Look for attribution like "said X", "X replied", "X asked"
2. In back-and-forth dialogue, speakers usually alternate
3. If someone just spoke in CONTEXT BEFORE, the DIALOGUE is likely a DIFFERENT person responding
4. Only name a speaker if you're confident
5. Return ONLY the speaker's name (e.g., "Jason") or "UNKNOWN" if unclear

SPEAKER:"""

    def find_speaker(
        self,
        dialogue: str,
        context_before: str,
        context_after: str,
    ) -> tuple[Optional[str], str]:
        """
        Find the speaker of a dialogue line using Ollama LLM.
        
        Returns: (speaker_name or None, method_description)
        """
        if not self._available:
            return None, "ollama_unavailable"
        
        prompt = self._build_prompt(dialogue, context_before, context_after)
        
        try:
            response = requests.post(
                f"{self._host}/api/generate",
                json={
                    "model": self._model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.1,
                        "num_predict": 20,
                    }
                },
                timeout=self.TIMEOUT_SECONDS
            )
            
            if response.status_code != 200:
                return None, f"ollama_error:{response.status_code}"
            
            result = response.json().get("response", "").strip()
            speaker = self._parse_speaker_response(result)
            
            if speaker:
                self.add_known_speaker(speaker)
                return speaker, "ollama"
            
            return None, "ollama_unknown"
            
        except requests.Timeout:
            return None, "ollama_timeout"
        except requests.RequestException as e:
            return None, f"ollama_error:{e}"
    
    def _parse_speaker_response(self, response: str) -> Optional[str]:
        """Parse the LLM response to extract speaker name."""
        if not response:
            return None
        
        # Clean up the response
        response = response.strip().strip('"\'').strip()
        
        # Check for unknown indicators
        unknown_indicators = ["unknown", "unclear", "cannot", "can't", "not sure", "n/a", "none"]
        if any(ind in response.lower() for ind in unknown_indicators):
            return None
        
        # Extract first word/name (handle "Jason." or "Jason said" etc.)
        words = response.split()
        if not words:
            return None
        
        speaker = words[0].strip('.,!?:;"\'')
        
        # Validate: should start with capital, not be a pronoun
        if not speaker or not speaker[0].isupper():
            return None
        if speaker.lower() in PRONOUNS:
            return None
        if speaker.lower() in NON_SPEAKER_WORDS:
            return None
        if len(speaker) < 2:
            return None
        
        return speaker


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
        enable_speaker_detection: bool = False,
        use_booknlp: bool = False,
        use_ollama: bool = False,
        book_slug: Optional[str] = None,
    ):
        self.narrator_voice = narrator_voice
        self.enable_speaker_detection = enable_speaker_detection
        self.book_slug = book_slug

        initial_pitch_shifts = None
        initial_genders = None
        
        if book_slug:
            from voice_mapping_store import VoiceMappingStore
            self._voice_store = VoiceMappingStore()
            saved = self._voice_store.load(book_slug)
            if saved["pitch_shifts"]:
                initial_pitch_shifts = saved["pitch_shifts"]
                initial_genders = saved["genders"]
        else:
            self._voice_store = None
        
        self.speaker_tracker = SpeakerTracker(
            initial_pitch_shifts, initial_genders
        )

        self._scene_break_pattern = re.compile("|".join(SCENE_BREAK_PATTERNS), re.MULTILINE)
        self._speaker_attribution_pattern = self._compile_speaker_pattern()
        
        self._spacy_detector = SpacySpeakerDetector()
        
        self._ollama_detector: Optional[OllamaSpeakerDetector] = None
        if use_ollama:
            detector = OllamaSpeakerDetector()
            if detector.is_available:
                self._ollama_detector = detector
        
        self._booknlp_detector: Optional[BookNLPSpeakerDetector] = None
        if use_booknlp:
            detector = BookNLPSpeakerDetector()
            if detector.is_available:
                self._booknlp_detector = detector
    
    def save_voice_mappings(self) -> None:
        if self._voice_store and self.book_slug:
            self._voice_store.save(
                self.book_slug,
                self.speaker_tracker.speaker_pitch_shifts,
                self.speaker_tracker.speaker_genders,
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
            if speaker:
                speaker_lower = speaker.lower()
                if speaker_lower not in PRONOUNS and speaker_lower not in NON_SPEAKER_WORDS:
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

    def _create_dialogue_segment(self, text: str, speaker: Optional[str], pitch_shift: float) -> TextSegment:
        return TextSegment(
            text=text,
            segment_type=SegmentType.DIALOGUE,
            speaker=speaker,
            pause_before_seconds=PAUSE_SECONDS["dialogue_start"],
            pause_after_seconds=PAUSE_SECONDS["dialogue_end"],
            speed=SPEED_BY_SEGMENT_TYPE[SegmentType.DIALOGUE],
            pitch_shift=pitch_shift,
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
            context_before = full_text[max(0, start - 200):start]
            context_after = full_text[end:min(len(full_text), end + 200)]
            
            if booknlp_attributions and (start, end) in booknlp_attributions:
                speaker = booknlp_attributions[(start, end)]
            elif self._ollama_detector and self._ollama_detector.is_available:
                speaker, _ = self._ollama_detector.find_speaker(
                    dialogue_text, context_before, context_after
                )
            elif self._spacy_detector.is_available:
                speaker, _ = self._spacy_detector.find_speaker(context_before, context_after)
            else:
                context_window = full_text[max(0, start - 100):min(len(full_text), end + 100)]
                speaker = self._extract_speaker_regex(context_window)

            pitch_shift = 0.0
            if self.enable_speaker_detection and speaker:
                pitch_shift = self.speaker_tracker.get_pitch_shift(speaker)

            segments.append(self._create_dialogue_segment(dialogue_text, speaker, pitch_shift))
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
        
        self._spacy_detector.reset_context()
        if self._ollama_detector:
            self._ollama_detector.reset_context()

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
                                pitch_shift=segment.pitch_shift,
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
                            pitch_shift=segment.pitch_shift,
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

    def get_speaker_pitch_map(self) -> dict[str, float]:
        return self.speaker_tracker.get_all_speakers()
    
    @property
    def using_booknlp(self) -> bool:
        return self._booknlp_detector is not None
    
    @property
    def using_ollama(self) -> bool:
        return self._ollama_detector is not None and self._ollama_detector.is_available
    
    @property
    def using_spacy(self) -> bool:
        return self._spacy_detector.is_available


def generate_silence_samples(duration_seconds: float, sample_rate: int = 24000) -> list[float]:
    return [0.0] * int(duration_seconds * sample_rate)


def pitch_shift_audio(audio: np.ndarray, sample_rate: int, semitones: float) -> np.ndarray:
    if semitones == 0 or len(audio) == 0:
        return audio
    
    from scipy import signal
    
    ratio = 2 ** (semitones / 12)
    new_length = int(len(audio) / ratio)
    if new_length == 0:
        return audio
    
    shifted = signal.resample(audio, new_length)
    return np.asarray(signal.resample(shifted, len(audio)))
