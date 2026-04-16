#!/usr/bin/env python3.12
import asyncio
import re
import shutil
import urllib.request
from pathlib import Path
from threading import Event
from typing import Optional

import numpy as np
import soundfile as sf
from pydub import AudioSegment
from ebooklib import epub, ITEM_DOCUMENT
from bs4 import BeautifulSoup
from kokoro_onnx import Kokoro

from config import MODEL_FILE, VOICES_FILE, MODEL_URL, VOICES_URL, MODELS_PATH, FINAL_PATH
from models import JobState, JobStatus, LogEvent
from job_manager import JobManager
from log_store import LogStore
from preprocessor import (
    ExpressivePreprocessor,
    ProcessedChapter,
    TextSegment,
    SegmentType,
    generate_silence_samples,
    pitch_shift_audio,
)


def download_models() -> bool:
    MODELS_PATH.mkdir(parents=True, exist_ok=True)
    
    for file_path, url in [(MODEL_FILE, MODEL_URL), (VOICES_FILE, VOICES_URL)]:
        if not file_path.exists():
            print(f"Downloading {file_path.name}...")
            try:
                urllib.request.urlretrieve(url, file_path)
                print(f"Downloaded {file_path.name}")
            except Exception as e:
                print(f"Failed to download {file_path.name}: {e}")
                return False
    return True


def extract_chapters_with_html(epub_path: str) -> list[dict]:
    book = epub.read_epub(epub_path)
    chapters = []
    
    for item in book.get_items():
        if item.get_type() == ITEM_DOCUMENT:
            html_content = item.get_body_content()
            soup = BeautifulSoup(html_content, "html.parser")
            text = soup.get_text().strip()
            
            if len(text) > 50:
                title_tag = soup.find(["h1", "h2", "h3", "title"])
                title = title_tag.get_text().strip() if title_tag else f"Chapter {len(chapters) + 1}"
                chapters.append({
                    "title": title,
                    "html_content": html_content,
                    "order": len(chapters) + 1
                })
    
    return chapters


class ConversionJob:
    def __init__(
        self,
        job_state: JobState,
        job_manager: JobManager,
        log_queue: asyncio.Queue[LogEvent],
        log_store: LogStore,
        enable_expressive: bool = True,
    ):
        self.job_state = job_state
        self.job_manager = job_manager
        self.log_queue = log_queue
        self.log_store = log_store
        self.should_stop = Event()
        self.kokoro: Optional[Kokoro] = None
        self.enable_expressive = enable_expressive
        self.sample_rate = 24000

    def _emit_log(self, level: str, message: str, progress: float = 0.0, chapter: Optional[int] = None, chunk: Optional[int] = None):
        event = LogEvent(
            level=level,
            message=message,
            progress=progress,
            chapter=chapter,
            chunk=chunk,
        )
        self.log_store.append(self.job_state.job_id, event)
        try:
            self.log_queue.put_nowait(event)
        except asyncio.QueueFull:
            pass

    def _init_kokoro(self) -> bool:
        if not MODEL_FILE.exists() or not VOICES_FILE.exists():
            self._emit_log("info", "Downloading TTS models (this may take a few minutes)...")
            if not download_models():
                self._emit_log("error", "Failed to download models")
                return False
            self._emit_log("info", "Models downloaded successfully")
        
        try:
            self.kokoro = Kokoro(str(MODEL_FILE), str(VOICES_FILE))
            return True
        except Exception as e:
            self._emit_log("error", f"Failed to initialize Kokoro: {e}")
            return False

    def _synthesize_segment(self, segment: TextSegment, default_voice: str) -> Optional[np.ndarray]:
        if not segment.text.strip():
            return None
        
        if self.kokoro is None:
            raise RuntimeError("Kokoro not initialized")
        
        lang = "en-gb" if default_voice.startswith("b") else "en-us"
        
        samples, sr = self.kokoro.create(
            segment.text,
            voice=default_voice,
            speed=segment.speed,
            lang=lang,
        )
        self.sample_rate = sr
        audio = np.array(samples)
        
        if segment.pitch_shift != 0:
            audio = pitch_shift_audio(audio, sr, segment.pitch_shift)
        
        return audio

    def _generate_silence(self, duration_seconds: float) -> np.ndarray:
        return np.array(generate_silence_samples(duration_seconds, self.sample_rate))

    def _process_chapter_expressive(
        self,
        chapter: ProcessedChapter,
        wav_file: sf.SoundFile,
        default_voice: str,
        chunk_index: int,
        total_chunks: int,
    ) -> int:
        chunks = self.preprocessor.chunk_segments(chapter.segments)
        
        for chunk_segments in chunks:
            if self.should_stop.is_set():
                return chunk_index
            
            for segment in chunk_segments:
                if segment.pause_before_seconds > 0:
                    silence = self._generate_silence(segment.pause_before_seconds)
                    wav_file.write(silence)
                
                if segment.segment_type == SegmentType.SCENE_BREAK:
                    self._emit_log("info", "  [SCENE BREAK]")
                    continue
                
                preview = segment.text[:60] + "..." if len(segment.text) > 60 else segment.text
                if segment.segment_type.value == "dialogue" and segment.speaker:
                    self._emit_log("info", f"  [{segment.speaker} {segment.pitch_shift:+.1f}st]: \"{preview}\"")
                elif segment.segment_type.value == "dialogue":
                    self._emit_log("info", f"  [DIALOGUE]: \"{preview}\"")
                elif segment.segment_type.value == "thought":
                    self._emit_log("info", f"  [THOUGHT]: {preview}")
                elif segment.segment_type.value == "chapter_start":
                    self._emit_log("info", f"  [CHAPTER]: {preview}")
                
                try:
                    audio = self._synthesize_segment(segment, default_voice)
                    if audio is not None:
                        wav_file.write(audio)
                except Exception as e:
                    self._emit_log("warning", f"Failed to synthesize segment: {e}")
                
                if segment.pause_after_seconds > 0:
                    silence = self._generate_silence(segment.pause_after_seconds)
                    wav_file.write(silence)
            
            chunk_index += 1
            progress = (chunk_index / total_chunks) * 100
            
            self._emit_log(
                "info",
                f"Processing chunk {chunk_index}/{total_chunks} (Chapter {chapter.order})",
                progress=progress,
                chapter=chapter.order,
                chunk=chunk_index,
            )
            
            self.job_manager.update_checkpoint(
                self.job_state.job_id,
                chapter.order,
                chunk_index,
                self.total_chapters,
                total_chunks,
            )
        
        return chunk_index

    def run(self) -> None:
        job_id = self.job_state.job_id
        output_dir = Path(self.job_state.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        self.job_manager.update_job(job_id, status=JobStatus.RUNNING)
        self._emit_log("info", "Starting conversion...")
        
        if not self._init_kokoro():
            self.job_manager.update_job(job_id, status=JobStatus.FAILED, error="Failed to initialize TTS")
            return
        
        try:
            raw_chapters = extract_chapters_with_html(self.job_state.epub_path)
            if not raw_chapters:
                self._emit_log("error", "No chapters found in EPUB")
                self.job_manager.update_job(job_id, status=JobStatus.FAILED, error="No chapters found")
                return
            
            from voice_mapping_store import VoiceMappingStore
            voice_store = VoiceMappingStore()
            book_slug = voice_store.get_book_slug(self.job_state.epub_filename)
            self._emit_log("info", f"Book: {book_slug}")
            
            self.preprocessor = ExpressivePreprocessor(
                narrator_voice=self.job_state.voice,
                enable_speaker_detection=False,
                use_booknlp=False,
                book_slug=book_slug,
            )
            
            self._emit_log("info", "Dialogue detection enabled (speaker attribution disabled)")
            
            processed_chapters: list[ProcessedChapter] = []
            total_chunks = 0
            
            self._emit_log("info", f"Preprocessing {len(raw_chapters)} chapters...")
            
            for i, raw_chapter in enumerate(raw_chapters, 1):
                chapter_title = raw_chapter.get("title", f"Chapter {i}")
                self._emit_log("info", f"Preprocessing chapter {i}/{len(raw_chapters)}: {chapter_title}")
                
                if self.preprocessor.using_booknlp:
                    self._emit_log("info", f"  Running BookNLP speaker detection...")
                
                processed = self.preprocessor.process_chapter_html(
                    raw_chapter["html_content"],
                    raw_chapter["title"],
                    raw_chapter["order"],
                )
                
                dialogue_count = sum(1 for s in processed.segments if s.segment_type.value == "dialogue")
                speakers_in_chapter = set(s.speaker for s in processed.segments if s.speaker)
                
                self._emit_log("info", f"  Found {len(processed.segments)} segments, {dialogue_count} dialogue lines")
                if speakers_in_chapter:
                    self._emit_log("info", f"  Speakers: {', '.join(speakers_in_chapter)}")
                
                processed_chapters.append(processed)
                total_chunks += len(self.preprocessor.chunk_segments(processed.segments))
            
            self.total_chapters = len(processed_chapters)
            self.job_manager.update_checkpoint(job_id, 0, 0, self.total_chapters, total_chunks)
            
            speaker_map = self.preprocessor.get_speaker_pitch_map()
            if len(speaker_map) > 1:
                speaker_list = ", ".join(f"{s}: {p:+.1f}st" for s, p in speaker_map.items() if s != "NARRATOR")
                self._emit_log("info", f"Detected speakers: {speaker_list}")
            
            self._emit_log("info", f"Found {self.total_chapters} chapters, {total_chunks} chunks")
            
            start_chunk = self.job_state.current_chunk
            chunk_index = 0
            
            for chapter in processed_chapters:
                if self.should_stop.is_set():
                    self._emit_log("info", "Conversion paused")
                    self.job_manager.update_job(job_id, status=JobStatus.PAUSED)
                    return
                
                chapter_wav_path = output_dir / f"chapter_{chapter.order:03d}.wav"
                chapter_mp3_path = output_dir / f"chapter_{chapter.order:03d}.mp3"
                
                chunks_in_chapter = len(self.preprocessor.chunk_segments(chapter.segments))
                
                if chunk_index + chunks_in_chapter <= start_chunk:
                    chunk_index += chunks_in_chapter
                    continue
                
                with sf.SoundFile(str(chapter_wav_path), mode='w', samplerate=self.sample_rate, channels=1) as wav_file:
                    chunk_index = self._process_chapter_expressive(
                        chapter,
                        wav_file,
                        self.job_state.voice,
                        chunk_index,
                        total_chunks,
                    )
                
                if self.should_stop.is_set():
                    if chapter_wav_path.exists():
                        chapter_wav_path.unlink()
                    self._emit_log("info", "Conversion paused")
                    self.job_manager.update_job(job_id, status=JobStatus.PAUSED)
                    return
                
                AudioSegment.from_wav(str(chapter_wav_path)).export(
                    str(chapter_mp3_path),
                    format="mp3",
                    bitrate="192k"
                )
                chapter_wav_path.unlink()
                self._emit_log("info", f"Saved {chapter_mp3_path.name}")
            
            self.preprocessor.save_voice_mappings()
            speaker_map = self.preprocessor.get_speaker_pitch_map()
            if len(speaker_map) > 1:
                self._emit_log("info", f"Saved pitch mappings for {len(speaker_map) - 1} speakers")
            
            self.job_manager.update_job(job_id, status=JobStatus.COMPLETED, progress=100.0)
            self._emit_log("info", "Conversion completed!", progress=100.0)
            
            self._copy_to_final_path(output_dir)
            
        except Exception as e:
            self._emit_log("error", f"Conversion failed: {e}")
            self.job_manager.update_job(job_id, status=JobStatus.FAILED, error=str(e))

    def _sanitize_filename(self, name: str) -> str:
        sanitized = re.sub(r'[<>:"/\\|?*]', '', name)
        sanitized = sanitized.strip('. ')
        return sanitized or "audiobook"

    def _copy_to_final_path(self, output_dir: Path) -> None:
        if not FINAL_PATH:
            return
        
        final_path = Path(FINAL_PATH)
        if not final_path.exists():
            try:
                final_path.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                self._emit_log("warning", f"Failed to create final path: {e}")
                return
        
        epub_name = Path(self.job_state.epub_filename).stem
        folder_name = self._sanitize_filename(epub_name)
        target_dir = final_path / folder_name
        
        if target_dir.exists():
            self._emit_log("info", f"Final folder already exists, overwriting: {target_dir}")
            shutil.rmtree(target_dir)
        
        target_dir.mkdir(parents=True, exist_ok=True)
        
        mp3_files = sorted(output_dir.glob("*.mp3"))
        for mp3_file in mp3_files:
            shutil.copy2(mp3_file, target_dir / mp3_file.name)
        
        self._emit_log("info", f"Copied {len(mp3_files)} files to {target_dir}")

    def stop(self) -> None:
        self.should_stop.set()
