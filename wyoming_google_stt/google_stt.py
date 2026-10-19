"""Asynchronous client for Google Cloud Speech-to-Text."""
import asyncio
import contextlib
import logging
from dataclasses import dataclass
from typing import AsyncIterator, Dict, List, Optional, Sequence, Tuple

from google.api_core.exceptions import InvalidArgument
from google.cloud import speech_v1
from google.oauth2 import service_account

from . import resolve_language

_LOGGER = logging.getLogger(__name__)

SAMPLE_RATE = 16000
SAMPLE_WIDTH = 2
CHANNELS = 1

# Google STT v1 speech adaptation limits.
MAX_PHRASES = 5000
MAX_PHRASE_LENGTH = 100

_END_OF_SINGLE_UTTERANCE = (
    speech_v1.StreamingRecognizeResponse.SpeechEventType.END_OF_SINGLE_UTTERANCE
)

# (phrases, boost) pairs; each becomes one SpeechContext.
PhraseSets = Sequence[Tuple[Sequence[str], float]]


@dataclass
class TranscriptionResult:
    """Result of a streaming transcription."""

    text: str
    language: Optional[str]
    audio_seconds: float


class AudioStream:
    """
    Audio chunks for one transcription, fed by the Wyoming handler.

    Chunks are kept so the stream can be replayed if Google rejects the first
    attempt. Once closed, new chunks are dropped so no more audio is uploaded.
    """

    def __init__(self) -> None:
        """Initialize an empty stream."""
        self._queue: asyncio.Queue[Optional[bytes]] = asyncio.Queue()
        self._received: List[bytes] = []
        self._ended = False
        self._drained = False
        self._closed = False

    @property
    def closed(self) -> bool:
        """True if no more audio will be uploaded."""
        return self._closed

    def put(self, audio: bytes) -> None:
        """Add an audio chunk (16 kHz, 16 bit, mono)."""
        if not self._closed and not self._ended:
            self._queue.put_nowait(audio)

    def end(self) -> None:
        """Signal the end of the audio."""
        if not self._ended:
            self._ended = True
            self._queue.put_nowait(None)

    def close(self) -> None:
        """Stop accepting audio, e.g. after the end of the utterance."""
        self._closed = True

    async def chunks(self, replay: bool = False) -> AsyncIterator[bytes]:
        """Yield audio chunks until the end of the stream or close()."""
        if replay:
            for chunk in self._received:
                yield chunk

        while not (self._closed or self._drained):
            chunk = await self._queue.get()
            if chunk is None:
                self._drained = True
                return
            self._received.append(chunk)
            yield chunk


def build_speech_contexts(phrase_sets: PhraseSets) -> List[speech_v1.SpeechContext]:
    """Build SpeechContexts, removing duplicates and respecting API limits."""
    contexts: List[speech_v1.SpeechContext] = []
    seen = set()
    for phrases, boost in phrase_sets:
        valid: List[str] = []
        for phrase in phrases:
            phrase = phrase.strip()
            key = phrase.lower()
            if not phrase or len(phrase) > MAX_PHRASE_LENGTH or key in seen:
                continue
            if len(seen) >= MAX_PHRASES:
                break
            seen.add(key)
            valid.append(phrase)

        if valid:
            context = speech_v1.SpeechContext(phrases=valid)
            if boost > 0:
                context.boost = boost
            contexts.append(context)

    return contexts


class GoogleSpeechTranscriberAsync:
    """Asynchronous client for Google Cloud Speech-to-Text with streaming."""

    def __init__(self, credentials_path: Optional[str] = None):
        """
        Initialize the async speech client.

        Parameters
        ----------
        credentials_path: Optional[str]
            Path to the Google service account JSON file.
            If None, uses default application credentials.

        """
        try:
            if credentials_path:
                _LOGGER.debug("Loading credentials from: %s", credentials_path)
                credentials = service_account.Credentials.from_service_account_file(
                    credentials_path
                )
                self.client = speech_v1.SpeechAsyncClient(credentials=credentials)
            else:
                _LOGGER.debug("Using default credentials (env var).")
                self.client = speech_v1.SpeechAsyncClient()
        except Exception:
            _LOGGER.exception("Failed to initialize SpeechAsyncClient")
            raise

        # Models that rejected single_utterance; they are not asked again.
        self._single_utterance_rejected: Dict[str, bool] = {}

    async def transcribe_streaming(
        self,
        audio: AudioStream,
        languages: Sequence[str],
        model: str,
        single_utterance: bool = True,
        phrase_sets: PhraseSets = (),
    ) -> TranscriptionResult:
        """
        Transcribe an audio stream asynchronously using Google Streaming API.

        Parameters
        ----------
        audio: AudioStream
            The audio to transcribe.
        languages: Sequence[str]
            Primary BCP-47 language code followed by up to 3 alternatives.
        model: str
            The recognition model to use (e.g., "latest_short").
        single_utterance: bool
            Stop after the first utterance. If the model rejects it, the
            request is retried once without it.
        phrase_sets: PhraseSets
            (phrases, boost) pairs to bias recognition.

        Returns
        -------
        TranscriptionResult
            The final transcript, detected language and seconds of audio sent.

        """
        if single_utterance and self._single_utterance_rejected.get(model):
            single_utterance = False

        speech_contexts = build_speech_contexts(phrase_sets)

        try:
            return await self._recognize(
                audio, languages, model, single_utterance, speech_contexts, False
            )
        except InvalidArgument as err:
            if not single_utterance:
                raise
            _LOGGER.warning(
                "Model '%s' rejected single_utterance (%s); retrying without it",
                model,
                err.message,
            )
            self._single_utterance_rejected[model] = True
            return await self._recognize(
                audio, languages, model, False, speech_contexts, True
            )

    async def _recognize(
        self,
        audio: AudioStream,
        languages: Sequence[str],
        model: str,
        single_utterance: bool,
        speech_contexts: List[speech_v1.SpeechContext],
        replay: bool,
    ) -> TranscriptionResult:
        """Run one StreamingRecognize call."""
        config = speech_v1.RecognitionConfig(
            encoding=speech_v1.RecognitionConfig.AudioEncoding.LINEAR16,
            sample_rate_hertz=SAMPLE_RATE,
            audio_channel_count=CHANNELS,
            language_code=languages[0],
            alternative_language_codes=list(languages[1:]),
            model=model,
            speech_contexts=speech_contexts,
        )
        streaming_config = speech_v1.StreamingRecognitionConfig(
            config=config,
            interim_results=False,
            single_utterance=single_utterance,
        )

        bytes_sent = 0

        async def request_generator():
            """Yield the config, then the audio chunks."""
            nonlocal bytes_sent
            yield speech_v1.StreamingRecognizeRequest(streaming_config=streaming_config)
            async for chunk in audio.chunks(replay=replay):
                bytes_sent += len(chunk)
                yield speech_v1.StreamingRecognizeRequest(audio_content=chunk)

        parts: List[str] = []
        language: Optional[str] = None

        responses = await self.client.streaming_recognize(requests=request_generator())
        try:
            async for response in responses:
                if response.speech_event_type == _END_OF_SINGLE_UTTERANCE:
                    # Google stops listening here; don't upload (and pay for)
                    # the rest of the audio.
                    _LOGGER.debug("End of single utterance detected")
                    audio.close()

                for result in response.results:
                    if not (result.is_final and result.alternatives):
                        continue
                    parts.append(result.alternatives[0].transcript.strip())
                    if result.language_code:
                        language = resolve_language(result.language_code, languages)

                if single_utterance and parts:
                    break
        finally:
            with contextlib.suppress(Exception):
                responses.cancel()

        audio.close()
        return TranscriptionResult(
            text=" ".join(part for part in parts if part),
            language=language,
            audio_seconds=bytes_sent / (SAMPLE_RATE * SAMPLE_WIDTH * CHANNELS),
        )
