"""Wyoming server for Google STT."""
import json
from functools import lru_cache
from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel, field_validator

_LANGUAGES_PATH = Path(__file__).parent / "languages.json"

# Google STT v1 allows up to 3 alternative languages per request.
MAX_ALTERNATIVE_LANGUAGES = 3


@lru_cache(maxsize=1)
def supported_languages() -> List[str]:
    """Return the language codes supported by Google STT (from languages.json)."""
    with open(_LANGUAGES_PATH, "r", encoding="utf-8") as languages_file:
        return json.load(languages_file)


def resolve_language(
    language: str, preferred: Optional[List[str]] = None
) -> Optional[str]:
    """
    Map a language code to a supported Google STT code.

    Home Assistant may send generic codes such as "es" or "en". Exact matches
    win, then a preferred code with the same base language (e.g. the configured
    "es-US" for "es"), then the first supported code with that base language.

    Returns None if no supported code matches.
    """
    languages = supported_languages()
    lowered = {code.lower(): code for code in languages}
    if language.lower() in lowered:
        return lowered[language.lower()]

    base = language.split("-")[0].lower()
    for candidate in (preferred or []) + languages:
        if candidate.split("-")[0].lower() == base:
            return candidate

    return None


class SpeechConfig(BaseModel):
    """
    Configuration for Google Speech-to-Text.

    Attributes:
    ----------
    language: str
        The primary language code for transcription (e.g., "en-US").
    alternative_languages: List[str]
        Alternative language codes to detect (max 3).
    model: str
        The recognition model to use (e.g., "latest_short", "command_and_search").
    single_utterance: bool
        Stop recognition (and audio upload) after the first utterance.
    phrases: List[str]
        Static words and phrases to boost recognition for.
    phrase_boost: float
        Boost for static phrases and Home Assistant terms (0-20).
    names_boost: float
        Boost for names sent by Home Assistant (entities, areas) (0-20).
    timeout: float
        Seconds to wait for Google after the audio stream ends.

    """

    language: str
    alternative_languages: List[str] = []
    model: str = "latest_short"
    single_utterance: bool = True
    phrases: List[str] = []
    phrase_boost: float = 10.0
    names_boost: float = 15.0
    timeout: float = 10.0

    @field_validator("language")
    @classmethod
    def _validate_language(cls, value: str) -> str:
        if value not in supported_languages():
            raise ValueError(f"Unsupported language code: {value}")
        return value

    @field_validator("alternative_languages")
    @classmethod
    def _validate_alternative_languages(cls, value: List[str]) -> List[str]:
        unsupported = [code for code in value if code not in supported_languages()]
        if unsupported:
            raise ValueError(f"Unsupported language codes: {', '.join(unsupported)}")
        if len(value) > MAX_ALTERNATIVE_LANGUAGES:
            raise ValueError(
                f"At most {MAX_ALTERNATIVE_LANGUAGES} alternative languages are allowed"
            )
        return value

    @field_validator("phrase_boost", "names_boost")
    @classmethod
    def _validate_boost(cls, value: float) -> float:
        if not 0 <= value <= 20:
            raise ValueError("Boost must be between 0 and 20")
        return value

    def languages_for(self, requested: Optional[str]) -> List[str]:
        """
        Return [primary, *alternatives] for a request.

        The requested language (if any) becomes the primary one, and the
        configured languages that differ from it are used as alternatives.
        """
        primary = self.language
        if requested:
            resolved = resolve_language(
                requested, [self.language, *self.alternative_languages]
            )
            if resolved:
                primary = resolved

        alternatives: List[str] = []
        for code in [self.language, *self.alternative_languages]:
            if code != primary and code not in alternatives:
                alternatives.append(code)

        return [primary, *alternatives[:MAX_ALTERNATIVE_LANGUAGES]]
