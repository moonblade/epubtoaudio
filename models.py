from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"


class VoiceOption(str, Enum):
    AF_ALLOY = "af_alloy"
    AF_AOEDE = "af_aoede"
    AF_BELLA = "af_bella"
    AF_HEART = "af_heart"
    AF_JESSICA = "af_jessica"
    AF_KORE = "af_kore"
    AF_NICOLE = "af_nicole"
    AF_NOVA = "af_nova"
    AF_RIVER = "af_river"
    AF_SARAH = "af_sarah"
    AF_SKY = "af_sky"
    AM_ADAM = "am_adam"
    AM_ECHO = "am_echo"
    AM_ERIC = "am_eric"
    AM_FENRIR = "am_fenrir"
    AM_LIAM = "am_liam"
    AM_MICHAEL = "am_michael"
    AM_ONYX = "am_onyx"
    AM_PUCK = "am_puck"
    BF_ALICE = "bf_alice"
    BF_EMMA = "bf_emma"
    BF_ISABELLA = "bf_isabella"
    BF_LILY = "bf_lily"
    BM_DANIEL = "bm_daniel"
    BM_FABLE = "bm_fable"
    BM_GEORGE = "bm_george"
    BM_LEWIS = "bm_lewis"


VOICE_DISPLAY_NAMES = {
    "af_alloy": "🇺🇸 Alloy (F)",
    "af_aoede": "🇺🇸 Aoede (F)",
    "af_bella": "🇺🇸 Bella (F)",
    "af_heart": "🇺🇸 Heart (F)",
    "af_jessica": "🇺🇸 Jessica (F)",
    "af_kore": "🇺🇸 Kore (F)",
    "af_nicole": "🇺🇸 Nicole (F)",
    "af_nova": "🇺🇸 Nova (F)",
    "af_river": "🇺🇸 River (F)",
    "af_sarah": "🇺🇸 Sarah (F)",
    "af_sky": "🇺🇸 Sky (F)",
    "am_adam": "🇺🇸 Adam (M) - Default",
    "am_echo": "🇺🇸 Echo (M)",
    "am_eric": "🇺🇸 Eric (M)",
    "am_fenrir": "🇺🇸 Fenrir (M)",
    "am_liam": "🇺🇸 Liam (M)",
    "am_michael": "🇺🇸 Michael (M)",
    "am_onyx": "🇺🇸 Onyx (M)",
    "am_puck": "🇺🇸 Puck (M)",
    "bf_alice": "🇬🇧 Alice (F)",
    "bf_emma": "🇬🇧 Emma (F)",
    "bf_isabella": "🇬🇧 Isabella (F)",
    "bf_lily": "🇬🇧 Lily (F)",
    "bm_daniel": "🇬🇧 Daniel (M)",
    "bm_fable": "🇬🇧 Fable (M)",
    "bm_george": "🇬🇧 George (M)",
    "bm_lewis": "🇬🇧 Lewis (M)",
}


class JobState(BaseModel):
    job_id: str
    status: JobStatus = JobStatus.PENDING
    voice: str = "am_adam"
    epub_filename: str = ""
    epub_path: str = ""
    output_dir: str = ""
    current_chapter: int = 0
    current_chunk: int = 0
    total_chapters: int = 0
    total_chunks: int = 0
    progress: float = 0.0
    error: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    model_config = {"use_enum_values": True}


class UploadResponse(BaseModel):
    job_id: str
    status: str
    message: str


class JobResponse(BaseModel):
    job_id: str
    status: str
    voice: str
    epub_filename: str
    progress: float
    current_chapter: int
    total_chapters: int
    error: Optional[str] = None
    created_at: str
    updated_at: str


class LogEvent(BaseModel):
    timestamp: datetime = Field(default_factory=datetime.now)
    level: str = "info"
    message: str
    progress: float = 0.0
    chapter: Optional[int] = None
    chunk: Optional[int] = None


class SegmentResponse(BaseModel):
    text: str
    segment_type: str
    speaker: Optional[str] = None
    pause_before_seconds: float
    pause_after_seconds: float
    speed: float
    pitch_shift: float


class ChapterResponse(BaseModel):
    title: str
    order: int
    segment_count: int
    speakers: list[str]
    segments: list[SegmentResponse]


class PreprocessResponse(BaseModel):
    filename: str
    total_chapters: int
    chapters: list[ChapterResponse]
    speaker_pitch_map: dict[str, float]


class BrowseFile(BaseModel):
    name: str
    path: str
    size: int
    modified: str


class BrowseResponse(BaseModel):
    enabled: bool
    current_path: str
    files: list[BrowseFile]
    directories: list[str]
