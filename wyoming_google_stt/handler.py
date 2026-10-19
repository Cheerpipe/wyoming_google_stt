"""Wyoming event handler for Google STT."""
import asyncio
import contextlib
import logging
from typing import List, Optional

from wyoming.asr import Transcribe, Transcript
from wyoming.audio import AudioChunk, AudioChunkConverter, AudioStart, AudioStop
from wyoming.event import Event
from wyoming.info import Describe, Info
from wyoming.server import AsyncEventHandler

from . import SpeechConfig
from .google_stt import (
    CHANNELS,
    SAMPLE_RATE,
    SAMPLE_WIDTH,
    AudioStream,
    GoogleSpeechTranscriberAsync,
    TranscriptionResult,
)

_LOGGER = logging.getLogger(__name__)


class GoogleEventHandler(AsyncEventHandler):
    """
    Wyoming event handler with asynchronous streaming to Google Cloud STT.

    Attributes
    ----------
    google_stt: GoogleSpeechTranscriberAsync
        The async client for Google STT.
    wyoming_info_event: Event
        The pre-computed Info event to send on Describe.
    speech_config: SpeechConfig
        The speech recognition configuration.
    _request: Transcribe
        The last Transcribe request (language, names, terms).
    _audio: Optional[AudioStream]
        Audio of the current transcription.
    _streaming_task: Optional[asyncio.Task]
        The background task handling the streaming transcription.

    """

    def __init__(
        self,
        google_stt: GoogleSpeechTranscriberAsync,
        wyoming_info: Info,
        speech_config: SpeechConfig,
        *args,
        **kwargs,
    ) -> None:
        """Initialize the event handler."""
        super().__init__(*args, **kwargs)
        self.google_stt = google_stt
        self.wyoming_info_event = wyoming_info.event()
        self.speech_config = speech_config

        self._request = Transcribe()
        self._converter = self._new_converter()
        self._audio: Optional[AudioStream] = None
        self._streaming_task: Optional[asyncio.Task] = None

    @staticmethod
    def _new_converter() -> AudioChunkConverter:
        """Create a converter to the format sent to Google."""
        return AudioChunkConverter(
            rate=SAMPLE_RATE, width=SAMPLE_WIDTH, channels=CHANNELS
        )

    async def _streaming_transcription(self, audio: AudioStream) -> TranscriptionResult:
        """Perform streaming transcription for the current request."""
        languages = self.speech_config.languages_for(self._request.language)
        terms: List[str] = [
            *self.speech_config.phrases,
            *(self._request.transcript_terms or []),
        ]
        phrase_sets = [
            (self._request.transcript_names or [], self.speech_config.names_boost),
            (terms, self.speech_config.phrase_boost),
        ]
        _LOGGER.debug(
            "Transcribing with languages=%s, names=%s, terms=%s",
            languages,
            len(self._request.transcript_names or []),
            len(terms),
        )

        return await self.google_stt.transcribe_streaming(
            audio=audio,
            languages=languages,
            model=self.speech_config.model,
            single_utterance=self.speech_config.single_utterance,
            phrase_sets=phrase_sets,
        )

    async def _cancel_transcription(self) -> None:
        """Cancel the current transcription, if any."""
        if self._streaming_task is not None:
            self._streaming_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._streaming_task
        self._streaming_task = None
        self._audio = None

    async def _finish_transcription(self) -> Transcript:
        """Wait for the transcription and build the (only) Transcript event."""
        assert self._audio is not None
        assert self._streaming_task is not None
        self._audio.end()

        try:
            result = await asyncio.wait_for(
                self._streaming_task, timeout=self.speech_config.timeout
            )
        except asyncio.TimeoutError:
            _LOGGER.error(
                "Google STT did not answer within %s seconds",
                self.speech_config.timeout,
            )
            return Transcript(text="")
        except Exception:  # pylint: disable=broad-exception-caught
            _LOGGER.exception("Error during streaming transcription")
            return Transcript(text="")
        finally:
            self._streaming_task = None
            self._audio = None

        _LOGGER.info(
            "Transcription completed (%.1fs of audio sent, language=%s): %s",
            result.audio_seconds,
            result.language,
            result.text,
        )
        return Transcript(text=result.text, language=result.language)

    async def handle_event(self, event: Event) -> bool:
        """Handle a single Wyoming event."""
        if Describe.is_type(event.type):
            await self.write_event(self.wyoming_info_event)
            _LOGGER.debug("Sent Wyoming info")
            return True

        if Transcribe.is_type(event.type):
            self._request = Transcribe.from_event(event)
            _LOGGER.debug("Transcribe request: language=%s", self._request.language)
            return True

        if AudioStart.is_type(event.type):
            _LOGGER.debug("Audio start received")
            await self._cancel_transcription()
            self._converter = self._new_converter()
            self._audio = AudioStream()
            self._streaming_task = asyncio.create_task(
                self._streaming_transcription(self._audio)
            )
            return True

        if AudioChunk.is_type(event.type):
            if self._audio is None:
                _LOGGER.warning("AudioChunk received before AudioStart")
                return True
            if self._audio.closed:
                # Google already has the full utterance; don't upload more.
                return True
            chunk = self._converter.convert(AudioChunk.from_event(event))
            # The converter may return a bytearray, which protobuf rejects.
            self._audio.put(bytes(chunk.audio))
            return True

        if AudioStop.is_type(event.type):
            _LOGGER.debug("Audio stop received")
            if self._audio is None:
                transcript = Transcript(text="")
            else:
                transcript = await self._finish_transcription()
            await self.write_event(transcript.event())
            self._request = Transcribe()
            return False  # End session

        return True

    async def disconnect(self) -> None:
        """Cancel any running transcription when the client disconnects."""
        await self._cancel_transcription()
