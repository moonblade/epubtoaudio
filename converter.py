import asyncio
import os
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

from config import MODEL_FILE, VOICES_FILE, MODEL_URL, VOICES_URL, MODELS_PATH
from models import JobState, JobStatus, LogEvent
from job_manager import JobManager
from log_store import LogStore


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


def extract_chapters_from_epub(epub_path: str) -> list[dict[str, str | int]]:
    book = epub.read_epub(epub_path)
    chapters = []
    
    for item in book.get_items():
        if item.get_type() == ITEM_DOCUMENT:
            soup = BeautifulSoup(item.get_body_content(), "html.parser")
            text = soup.get_text().strip()
            if len(text) > 50:
                title_tag = soup.find(["h1", "h2", "h3", "title"])
                title = title_tag.get_text().strip() if title_tag else f"Chapter {len(chapters) + 1}"
                chapters.append({
                    "title": title,
                    "content": text,
                    "order": len(chapters) + 1
                })
    
    return chapters


def chunk_text(text: str, max_size: int = 1000) -> list[str]:
    sentences = text.replace('\n', ' ').split('.')
    chunks = []
    current_chunk = []
    current_size = 0
    
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        sentence = sentence + '.'
        sentence_size = len(sentence)
        
        if sentence_size > max_size:
            if current_chunk:
                chunks.append(' '.join(current_chunk))
                current_chunk = []
                current_size = 0
            
            words = sentence.split()
            piece = []
            piece_size = 0
            for word in words:
                if piece_size + len(word) + 1 > max_size:
                    if piece:
                        chunks.append(' '.join(piece))
                    piece = [word]
                    piece_size = len(word)
                else:
                    piece.append(word)
                    piece_size += len(word) + 1
            if piece:
                chunks.append(' '.join(piece))
            continue
        
        if current_size + sentence_size > max_size and current_chunk:
            chunks.append(' '.join(current_chunk))
            current_chunk = []
            current_size = 0
        
        current_chunk.append(sentence)
        current_size += sentence_size
    
    if current_chunk:
        chunks.append(' '.join(current_chunk))
    
    return chunks


class ConversionJob:
    def __init__(
        self,
        job_state: JobState,
        job_manager: JobManager,
        log_queue: asyncio.Queue[LogEvent],
        log_store: LogStore,
    ):
        self.job_state = job_state
        self.job_manager = job_manager
        self.log_queue = log_queue
        self.log_store = log_store
        self.should_stop = Event()
        self.kokoro: Optional[Kokoro] = None

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
            chapters = extract_chapters_from_epub(self.job_state.epub_path)
            if not chapters:
                self._emit_log("error", "No chapters found in EPUB")
                self.job_manager.update_job(job_id, status=JobStatus.FAILED, error="No chapters found")
                return
            
            all_chunks = []
            for chapter in chapters:
                chapter_chunks = chunk_text(str(chapter["content"]))
                for chunk in chapter_chunks:
                    all_chunks.append({"chapter": chapter["order"], "title": chapter["title"], "text": chunk})
            
            total_chunks = len(all_chunks)
            self.job_manager.update_checkpoint(job_id, 0, 0, len(chapters), total_chunks)
            self._emit_log("info", f"Found {len(chapters)} chapters, {total_chunks} chunks")
            
            start_chunk = self.job_state.current_chunk
            sample_rate = 24000
            current_chapter = 0
            chapter_wav_file: Optional[sf.SoundFile] = None
            
            for i, chunk_data in enumerate(all_chunks):
                if i < start_chunk:
                    continue
                
                if self.should_stop.is_set():
                    if chapter_wav_file:
                        chapter_wav_file.close()
                    self._emit_log("info", "Conversion paused")
                    self.job_manager.update_job(job_id, status=JobStatus.PAUSED)
                    return
                
                chapter_num = chunk_data["chapter"]
                progress = ((i + 1) / total_chunks) * 100
                
                if chapter_num != current_chapter:
                    if chapter_wav_file:
                        chapter_wav_file.close()
                        chapter_wav_path = output_dir / f"chapter_{current_chapter:03d}.wav"
                        chapter_mp3_path = output_dir / f"chapter_{current_chapter:03d}.mp3"
                        AudioSegment.from_wav(str(chapter_wav_path)).export(str(chapter_mp3_path), format="mp3", bitrate="192k")
                        chapter_wav_path.unlink()
                        self._emit_log("info", f"Saved {chapter_mp3_path.name}")
                    
                    current_chapter = chapter_num
                    chapter_wav_path = output_dir / f"chapter_{chapter_num:03d}.wav"
                    chapter_wav_file = sf.SoundFile(str(chapter_wav_path), mode='w', samplerate=sample_rate, channels=1)
                
                self._emit_log(
                    "info",
                    f"Processing chunk {i + 1}/{total_chunks} (Chapter {chapter_num})",
                    progress=progress,
                    chapter=chapter_num,
                    chunk=i + 1,
                )
                
                try:
                    voice = self.job_state.voice
                    lang = "en-gb" if voice.startswith("b") else "en-us"
                    if self.kokoro is None:
                        raise RuntimeError("Kokoro not initialized")
                    samples, sr = self.kokoro.create(
                        chunk_data["text"],
                        voice=voice,
                        speed=1.0,
                        lang=lang,
                    )
                    sample_rate = sr
                    
                    if chapter_wav_file:
                        chapter_wav_file.write(np.array(samples))
                    
                except Exception as e:
                    self._emit_log("warning", f"Failed to process chunk {i + 1}: {e}")
                
                self.job_manager.update_checkpoint(job_id, chapter_num, i + 1, len(chapters), total_chunks)
            
            if chapter_wav_file:
                chapter_wav_file.close()
                chapter_wav_path = output_dir / f"chapter_{current_chapter:03d}.wav"
                chapter_mp3_path = output_dir / f"chapter_{current_chapter:03d}.mp3"
                AudioSegment.from_wav(str(chapter_wav_path)).export(str(chapter_mp3_path), format="mp3", bitrate="192k")
                chapter_wav_path.unlink()
                self._emit_log("info", f"Saved {chapter_mp3_path.name}")
            
            self.job_manager.update_job(job_id, status=JobStatus.COMPLETED, progress=100.0)
            self._emit_log("info", "Conversion completed!", progress=100.0)
            
        except Exception as e:
            self._emit_log("error", f"Conversion failed: {e}")
            self.job_manager.update_job(job_id, status=JobStatus.FAILED, error=str(e))

    def stop(self) -> None:
        self.should_stop.set()
