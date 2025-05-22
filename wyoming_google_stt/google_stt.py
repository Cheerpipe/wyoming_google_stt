import logging
from typing import Optional, List, AsyncIterable

from google.cloud import speech_v1, speech
from google.api_core.exceptions import GoogleAPIError
from google.oauth2 import service_account

_LOGGER = logging.getLogger(__name__)

DEFAULT_LANGUAGE = "en-US"
DEFAULT_SAMPLE_RATE = 16000

class GoogleSpeechTranscriberAsync:
    """Cliente asíncrono para Google Cloud Speech-to-Text con streaming."""

    def __init__(self, credentials_path: Optional[str] = None):
        try:
            if credentials_path:
                _LOGGER.debug("Loading credentials from: %s", credentials_path)
                credentials = service_account.Credentials.from_service_account_file(credentials_path)
                self.client = speech_v1.SpeechAsyncClient(credentials=credentials)
            else:
                _LOGGER.debug("Using default credentials.")
                self.client = speech_v1.SpeechAsyncClient()
        except Exception:
            _LOGGER.exception("Failed to initialize SpeechAsyncClient")
            raise

    def _build_config(
        self,
        language_code: str,
        alternative_language_codes: Optional[List[str]],
        model: Optional[str],
        phrases: List[str] = [],
    ):
        return speech_v1.RecognitionConfig(
            encoding=speech_v1.RecognitionConfig.AudioEncoding.LINEAR16,
            sample_rate_hertz=DEFAULT_SAMPLE_RATE,
            language_code=language_code,
            alternative_language_codes=alternative_language_codes or [],
            model=model or "",
            speech_contexts = [
                    speech.SpeechContext(
                        phrases=phrases,
                        boost=20.0)] # Todo: Param
        )

    async def transcribe_streaming(
        self,
        audio_async_generator: AsyncIterable[bytes],
        language_code: str = DEFAULT_LANGUAGE,
        alternative_language_codes: Optional[List[str]] = None,
        model: Optional[str] = None,
        phrases: List[str] = [],
    ) -> str:
        """Transcribe audio stream async con Google Streaming API."""
        config = self._build_config(language_code, alternative_language_codes, model, phrases)
        streaming_config = speech_v1.StreamingRecognitionConfig(
            config=config,
            interim_results=False,
            single_utterance=True,
        )

        async def request_generator():
            # El primer request debe tener solo la configuración
            yield speech_v1.StreamingRecognizeRequest(streaming_config=streaming_config)
            # Luego, enviar chunks de audio
            async for chunk in audio_async_generator:
                yield speech_v1.StreamingRecognizeRequest(audio_content=chunk)

        transcript = ""

        try:
            responses = await self.client.streaming_recognize(requests=request_generator())

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
