"""Wyoming server for Google STT."""
from typing import List, Literal

from pydantic import BaseModel

# List of valid language codes for Google STT.
# This is used for type validation in SpeechConfig.
LANGUAGE_CODES = Literal[
    "af-ZA",
    "am-ET",
    "ar-AE",
    "ar-BH",
    "ar-DZ",
    "ar-EG",
    "ar-IL",
    "ar-IQ",
    "ar-JO",
    "ar-KW",
    "ar-LB",
    "ar-MA",
    "ar-OM",
    "ar-PS",
    "ar-QA",
    "ar-SA",
    "ar-TN",
    "ar-YE",
    "az-AZ",
    "be-BY",
    "bg-BG",
    "bn-BD",
    "bn-IN",
    "bs-BA",
    "ca-ES",
    "cs-CZ",
    "da-DK",
    "de-DE",
    "el-GR",
    "en-AU",
    "en-CA",
    "en-GB",
    "en-GH",
    "en-HK",
    "en-IE",
    "en-IN",
    "en-KE",
    "en-NG",
    "en-NZ",
    "en-PH",
    "en-PK",
    "en-SG",
    "en-TZ",
    "en-US",
    "en-ZA",
    "es-AR",
    "es-BO",
    "es-CL",
    "es-CO",
    "es-CR",
    "es-DO",
    "es-EC",
    "es-ES",
    "es-GT",
    "es-HN",
    "es-MX",
    "es-NI",
    "es-PA",
    "es-PE",
    "es-PR",
    "es-PY",
    "es-SV",
    "es-US",
    "es-UY",
    "es-VE",
    "et-EE",
    "eu-ES",
    "fa-IR",
    "fi-FI",
    "fil-PH",
    "fr-BE",
    "fr-CA",
    "fr-CH",
    "fr-FR",
    "gl-ES",
    "gu-IN",
    "he-IL",
    "hi-IN",
    "hr-HR",
    "hu-HU",
    "hy-AM",
    "id-ID",
    "is-IS",
    "it-IT",
    "ja-JP",
    "jv-ID",
    "ka-GE",
    "kk-KZ",
    "km-KH",
    "kn-IN",
    "ko-KR",
    "lo-LA",
    "lt-LT",
    "lv-LV",
    "mk-MK",
    "ml-IN",
    "mn-MN",
    "mr-IN",
    "ms-MY",
    "my-MM",
    "ne-NP",
    "nl-BE",
    "nl-NL",
    "no-NO",
    "pa-Guru-IN",
    "pl-PL",
    "pt-BR",
    "pt-PT",
    "ro-RO",
    "ru-RU",
    "si-LK",
    "sk-SK",
    "sl-SI",
    "sq-AL",
    "sr-RS",
    "su-ID",
    "sv-SE",
    "sw-KE",
    "sw-TZ",
    "ta-IN",
    "te-IN",
    "th-TH",
    "tr-TR",
    "uk-UA",
    "ur-IN",
    "ur-PK",
    "uz-UZ",
    "vi-VN",
    "zh-CN",
    "zh-HK",
    "zh-TW",
    "zu-ZA",
]


class SpeechConfig(BaseModel):
    """
    Configuration for Google Speech-to-Text.

    Attributes:
    ----------
    language: str
        The primary language code for transcription (e.g., "en-US").
    alternative_languages: list[LANGUAGE_CODES]
        A list of alternative language codes to detect.
    model: str
        The recognition model to use (e.g., "latest_short", "phone_call").
    phrases: List[str]
        A list of words and phrases to boost recognition for.
    phrase_boost: float
        The strength of the boost to apply to provided phrases (0-20).

    """

    language: str
    alternative_languages: list[LANGUAGE_CODES] = ["en-US"]
    model: str = "latest_short"
    phrases: List[str] = []
    phrase_boost: float = 20.0