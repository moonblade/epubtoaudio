#!/usr/bin/env python3.12
"""
Persistent voice mapping storage for consistent character voices across chapters.

Stores speaker-to-voice assignments per book, so when converting multiple chapters
of the same book, characters maintain their assigned voices.
"""

import json
import re
from pathlib import Path
from typing import Any, Optional

from config import VOICE_MAPPINGS_PATH


def extract_book_title(filename: str) -> str:
    """
    Extract book title from filename pattern: "date - book title - chapter title"
    
    Examples:
        "2026-04-15 - The Legend of William Oh - Chapter 262.epub" -> "the-legend-of-william-oh"
        "The Primal Hunter - Book 1 - Chapter 5.epub" -> "the-primal-hunter"
        "wanderingInn2.epub" -> "wanderinginn2"
    """
    name = Path(filename).stem
    
    date_pattern = r'^\d{4}-\d{2}-\d{2}\s*-\s*'
    name = re.sub(date_pattern, '', name)
    
    chapter_patterns = [
        r'\s*-\s*[Cc]hapter\s*\d+.*$',
        r'\s*-\s*[Cc]h\s*\d+.*$',
        r'\s*[Cc]hapter\s*\d+.*$',
        r'\s*-\s*[Bb]ook\s*\d+.*$',
        r'\s*-\s*[Pp]art\s*\d+.*$',
    ]
    
    for pattern in chapter_patterns:
        name = re.sub(pattern, '', name)
    
    slug = name.lower().strip()
    slug = re.sub(r'[^a-z0-9]+', '-', slug)
    slug = re.sub(r'^-+|-+$', '', slug)
    
    return slug or "unknown"


class VoiceMappingStore:
    def __init__(self, storage_path: Optional[Path] = None):
        self.storage_path = storage_path or VOICE_MAPPINGS_PATH
        self.storage_path.mkdir(parents=True, exist_ok=True)
    
    def _get_mapping_file(self, book_slug: str) -> Path:
        return self.storage_path / f"{book_slug}.json"
    
    def load(self, book_slug: str) -> dict[str, Any]:
        """
        Load voice mappings for a book.
        
        Returns dict with:
            - "speakers": {speaker_name: voice_id}
            - "genders": {speaker_name: gender}
            - "narrator_voice": voice_id
        """
        mapping_file = self._get_mapping_file(book_slug)
        
        if mapping_file.exists():
            try:
                data = json.loads(mapping_file.read_text())
                return {
                    "speakers": data.get("speakers", {}),
                    "genders": data.get("genders", {}),
                    "narrator_voice": data.get("narrator_voice", "am_adam"),
                    "used_voices": set(data.get("used_voices", [])),
                }
            except (json.JSONDecodeError, KeyError):
                pass
        
        return {
            "speakers": {},
            "genders": {},
            "narrator_voice": "am_adam",
            "used_voices": set(),
        }
    
    def save(self, book_slug: str, speakers: dict[str, str], genders: dict[str, str], 
             narrator_voice: str, used_voices: set[str]) -> None:
        """Save voice mappings for a book."""
        mapping_file = self._get_mapping_file(book_slug)
        
        data = {
            "speakers": speakers,
            "genders": genders,
            "narrator_voice": narrator_voice,
            "used_voices": list(used_voices),
        }
        
        mapping_file.write_text(json.dumps(data, indent=2))
    
    def get_book_slug(self, filename: str) -> str:
        """Extract book slug from filename."""
        return extract_book_title(filename)
    
    def list_books(self) -> list[str]:
        """List all books with saved voice mappings."""
        return [f.stem for f in self.storage_path.glob("*.json")]
    
    def get_mapping_summary(self, book_slug: str) -> Optional[dict[str, Any]]:
        """Get a summary of voice mappings for display."""
        mapping = self.load(book_slug)
        if not mapping["speakers"]:
            return None
        
        return {
            "book": book_slug,
            "narrator": mapping["narrator_voice"],
            "characters": len(mapping["speakers"]) - 1,
            "speakers": mapping["speakers"],
        }
