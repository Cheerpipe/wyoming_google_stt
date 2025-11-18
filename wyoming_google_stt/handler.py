"""Wyoming event handler for Google STT."""
import asyncio
import logging
from typing import AsyncIterable, Optional

from wyoming.asr import Transcribe, Transcript
from wyoming.audio import AudioChunk, AudioStart, AudioStop
from wyoming.event import Event
from wyoming.info import Describe, Info
from wyoming.server import AsyncEventHandler

from . import SpeechConfig
from .google_stt import GoogleSpeechTranscriberAsync

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
    _language: str
        The current language code for transcription.
    _audio_queue: Optional[asyncio.Queue[Optional[bytes]]]
        Queue for passing audio chunks to the streaming task.
        `None` indicates the end of the stream.
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
        self._language = speech_config.language

        self._audio_queue: Optional[asyncio.Queue[Optional[bytes]]] = None
        self._streaming_task: Optional[asyncio.Task] = None

    async def _audio_generator(self) -> AsyncIterable[bytes]:
        """Async generator that yields audio chunks for Google Streaming."""
        assert self._audio_queue is not None
        while True:
            chunk = await self._audio_queue.get()
            if chunk is None:
                # End of stream signal
                break
            yield chunk

    async def _streaming_transcription(self):
        """Task that performs streaming transcription and publishes results."""
        assert self._audio_queue is not None

        try:
            text = await self.google_stt.transcribe_streaming(
                audio_async_generator=self._audio_generator(),
                language_code=self._language,
                alternative_language_codes=(
                    self.speech_config.alternative_languages
                ),
                model=self.speech_config.model,
                phrases=self.speech_config.phrases,
                phrase_boost=self.speech_config.phrase_boost,
            )
            await self.write_event(Transcript(text=text).event())
            _LOGGER.info("Transcription completed: %s", text)

        except asyncio.CancelledError:
            # Expected on graceful shutdown (AudioStop event).
            _LOGGER.debug("Streaming transcription task was cancelled.")
        except Exception:
            _LOGGER.exception("Error during streaming transcription")
            await self.write_event(Transcript(text="").event())

    async def handle_event(self, event: Event) -> bool:
        """Handle a single Wyoming event."""
        if Describe.is_type(event.type):
            await self.write_event(self.wyoming_info_event)
            _LOGGER.debug("Sent Wyoming info")
            return True

        if AudioStart.is_type(event.type):
            _LOGGER.debug("Audio start received")
            # CRITICAL RELIABILITY: Use a bounded queue to apply backpressure.
            # Maxsize limits memory usage if Google STT is slow to consume.
            self._audio_queue = asyncio.Queue(maxsize=16)
            # Run the streaming task in the background
            self._streaming_task = asyncio.create_task(
                self._streaming_transcription()
            )
            return True

        if AudioChunk.is_type(event.type):
            chunk = AudioChunk.from_event(event)
            if self._audio_queue is not None:
                # This await may block if the queue is full (backpressure)
                await self._audio_queue.put(chunk.audio)
            else:
                _LOGGER.warning("AudioChunk received but queue is None")
            return True

        if AudioStop.is_type(event.type):
            _LOGGER.debug("Audio stop received")
            if self._audio_queue is not None:
                # Signal the end of the stream
                await self._audio_queue.put(None)
            if self._streaming_task is not None:
                # Wait for the transcription to finish (or be cancelled)
                await self._streaming_task
                self._streaming_task = None
            self._audio_queue = None
            return False  # End session

        if Transcribe.is_type(event.type):
            transcribe = Transcribe.from_event(event)
            if transcribe.language:
                self._language = transcribe.language
                _LOGGER.debug("Updated language to %s", self._language)
            return True

        return True