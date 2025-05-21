import asyncio
import logging
from typing import Optional, AsyncIterable

from wyoming.asr import Transcribe, Transcript
from wyoming.audio import AudioChunk, AudioStart, AudioStop
from wyoming.event import Event
from wyoming.info import Describe, Info
from wyoming.server import AsyncEventHandler

from . import SpeechConfig
from .google_stt import GoogleSpeechTranscriberAsync

_LOGGER = logging.getLogger(__name__)

class GoogleEventHandler(AsyncEventHandler):
    """Wyoming event handler con streaming asíncrono hacia Google Cloud STT."""

    def __init__(
        self,
        google_stt: GoogleSpeechTranscriberAsync,
        wyoming_info: Info,
        speech_config: SpeechConfig,
        model_lock: asyncio.Lock,
        *args,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.google_stt = google_stt
        self.wyoming_info_event = wyoming_info.event()
        self.speech_config = speech_config
        self.model_lock = model_lock
        self._language = speech_config.language

        self._audio_queue: Optional[asyncio.Queue[bytes]] = None
        self._streaming_task: Optional[asyncio.Task] = None

    async def _audio_generator(self) -> AsyncIterable[bytes]:
        """Generador async que produce chunks de audio para Google Streaming."""
        assert self._audio_queue is not None
        while True:
            chunk = await self._audio_queue.get()
            if chunk is None:
                break
            yield chunk

    async def _streaming_transcription(self):
        """Tarea que hace la transcripción streaming y publica resultados."""
        assert self._audio_queue is not None

        try:
            text = await self.google_stt.transcribe_streaming(
                audio_async_generator=self._audio_generator(),
                language_code=self._language,
                alternative_language_codes=self.speech_config.alternative_languages,
                model=self.speech_config.model,
            )
            await self.write_event(Transcript(text=text).event())
            _LOGGER.info("Transcription completed: %s", text)

        except Exception:
            _LOGGER.exception("Error during streaming transcription")
            await self.write_event(Transcript(text="").event())

    async def handle_event(self, event: Event) -> bool:
        if Describe.is_type(event.type):
            await self.write_event(self.wyoming_info_event)
            _LOGGER.debug("Sent Wyoming info")
            return True

        if AudioStart.is_type(event.type):
            _LOGGER.debug("Audio start received")
            self._audio_queue = asyncio.Queue()
            # Ejecuta la tarea de streaming en segundo plano
            self._streaming_task = asyncio.create_task(self._streaming_transcription())
            return True

        if AudioChunk.is_type(event.type):
            chunk = AudioChunk.from_event(event)
            if self._audio_queue is not None:
                await self._audio_queue.put(chunk.audio)
            else:
                _LOGGER.warning("AudioChunk received but queue is None")
            return True

        if AudioStop.is_type(event.type):
            _LOGGER.debug("Audio stop received")
            if self._audio_queue is not None:
                # Señalamos el fin del stream
                await self._audio_queue.put(None)
            if self._streaming_task is not None:
                await self._streaming_task
                self._streaming_task = None
            self._audio_queue = None
            return False  # Terminar sesión

        if Transcribe.is_type(event.type):
            transcribe = Transcribe.from_event(event)
            if transcribe.language:
                self._language = transcribe.language
                _LOGGER.debug("Updated language to %s", self._language)
            return True

        return True
