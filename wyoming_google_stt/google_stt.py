"""Asynchronous client for Google Cloud Speech-to-Text."""
import logging
from typing import AsyncIterable, List, Optional

from google.api_core.exceptions import GoogleAPIError
from google.cloud import speech, speech_v1
from google.oauth2 import service_account

_LOGGER = logging.getLogger(__name__)

DEFAULT_LANGUAGE = "en-US"
DEFAULT_SAMPLE_RATE = 16000


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
                credentials = (
                    service_account.Credentials.from_service_account_file(
                        credentials_path
                    )
                )
                self.client = speech_v1.SpeechAsyncClient(
                    credentials=credentials
                )
            else:
                _LOGGER.debug("Using default credentials (env var).")
                self.client = speech_v1.SpeechAsyncClient()
        except Exception:
            _LOGGER.exception("Failed to initialize SpeechAsyncClient")
            raise

    def _build_config(
        self,
        language_code: str,
        alternative_language_codes: Optional[List[str]],
        model: Optional[str],
        phrases: List[str],
        phrase_boost: float,
    ) -> speech_v1.RecognitionConfig:
        """
        Build the recognition configuration for the Google API.

        Parameters
        ----------
        language_code: str
            Primary language code.
        alternative_language_codes: Optional[List[str]]
            List of other possible language codes.
        model: Optional[str]
            The specific recognition model to use.
        phrases: List[str]
            List of phrases to boost.
        phrase_boost: float
            The boost strength (0-20).

        Returns
        -------
        speech_v1.RecognitionConfig
            The configured recognition object.

        """
        speech_contexts = []
        if phrases:
            speech_contexts.append(
                speech.SpeechContext(phrases=phrases, boost=phrase_boost)
            )

        return speech_v1.RecognitionConfig(
            encoding=speech_v1.RecognitionConfig.AudioEncoding.LINEAR16,
            sample_rate_hertz=DEFAULT_SAMPLE_RATE,
            language_code=language_code,
            alternative_language_codes=alternative_language_codes or [],
            model=model or "",
            speech_contexts=speech_contexts,
        )

    async def transcribe_streaming(
        self,
        audio_async_generator: AsyncIterable[bytes],
        language_code: str = DEFAULT_LANGUAGE,
        alternative_language_codes: Optional[List[str]] = None,
        model: Optional[str] = None,
        phrases: List[str] = [],
        phrase_boost: float = 20.0,
    ) -> str:
        """
        Transcribe an audio stream asynchronously using Google Streaming API.

        Parameters
        ----------
        audio_async_generator: AsyncIterable[bytes]
            An asynchronous generator yielding audio chunks.
        language_code: str
            The primary BCP-47 language code for transcription.
        alternative_language_codes: Optional[List[str]]
            A list of secondary BCP-47 language codes.
        model: Optional[str]
            The recognition model to use (e.g., "latest_short").
        phrases: List[str]
            A list of phrases to boost recognition for.
        phrase_boost: float
            The strength to apply to the phrase boost.

        Returns
        -------
        str
            The final transcribed text.

        Raises
        ------
        GoogleAPIError
            If an error occurs during the streaming recognition.
        Exception
            For other unexpected errors.

        """
        config = self._build_config(
            language_code,
            alternative_language_codes,
            model,
            phrases,
            phrase_boost,
        )
        streaming_config = speech_v1.StreamingRecognitionConfig(
            config=config,
            interim_results=False,
            single_utterance=True,
        )

        async def request_generator():
            """Yield streaming recognize requests."""
            # The first request must contain only the configuration
            yield speech_v1.StreamingRecognizeRequest(
                streaming_config=streaming_config
            )
            # Subsequent requests contain audio chunks
            async for chunk in audio_async_generator:
                yield speech_v1.StreamingRecognizeRequest(audio_content=chunk)

        transcript = ""

        try:
            responses = await self.client.streaming_recognize(
                requests=request_generator()
            )

            async for response in responses:
                for result in response.results:
                    if result.is_final and result.alternatives:
                        transcript += result.alternatives[0].transcript + " "

            return transcript.strip()

        except GoogleAPIError:
            _LOGGER.exception("Error during streaming recognition")
            raise
        except Exception:
            _LOGGER.exception("Unexpected error during streaming transcription")
            raise