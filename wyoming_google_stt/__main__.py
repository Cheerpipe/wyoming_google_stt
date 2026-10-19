"""Wyoming server for Google STT."""
import argparse
import asyncio
import logging
import os
import sys
from functools import partial

from pydantic import ValidationError
from wyoming.info import AsrModel, AsrProgram, Attribution, Info
from wyoming.server import AsyncServer

from . import SpeechConfig, supported_languages
from .google_stt import GoogleSpeechTranscriberAsync
from .handler import GoogleEventHandler
from .version import __version__

_LOGGER = logging.getLogger(__name__)

REPOSITORY_URL = "https://github.com/Cheerpipe/wyoming_google_stt"


def _env_flag(name: str) -> bool:
    """Return True if an environment variable is set to a truthy value."""
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


def parse_arguments():
    """Parse command-line arguments (defaults can come from env vars)."""
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--uri", default="tcp://0.0.0.0:10300", help="unix:// or tcp://"
    )
    parser.add_argument(
        "--language",
        default=os.environ.get("LANGUAGE", "es-US"),
        help=(
            "Primary language for transcription (e.g., en-US, es-ES) "
            "(Default: es-US, env: LANGUAGE)"
        ),
    )
    parser.add_argument(
        "--alternative-languages",
        nargs="*",
        default=os.environ.get("ALTERNATIVE_LANGUAGES", "en-US").split(),
        help=(
            "Up to 3 secondary languages for transcription "
            "(e.g., en-US fr-FR) (Default: en-US, env: ALTERNATIVE_LANGUAGES)"
        ),
    )
    parser.add_argument(
        "--model",
        default=os.environ.get("MODEL", "latest_short"),
        help=(
            "Model name (e.g., latest_short, command_and_search) "
            "(Default: latest_short, env: MODEL)"
        ),
    )
    parser.add_argument(
        "--single-utterance",
        action=argparse.BooleanOptionalAction,
        default=not _env_flag("DISABLE_SINGLE_UTTERANCE"),
        help=(
            "Stop recognition and audio upload after the first utterance "
            "(Default: enabled)"
        ),
    )
    parser.add_argument(
        "--phrases",
        nargs="*",
        default=[],
        help=(
            "Phrases to boost with SpeechContext "
            "(e.g., 'turn on the light' 'turn off the fan')"
        ),
    )
    parser.add_argument(
        "--phrase-boost",
        type=float,
        default=10.0,
        help="Boost for --phrases and terms sent by Home Assistant (0-20) "
        "(Default: 10.0)",
    )
    parser.add_argument(
        "--names-boost",
        type=float,
        default=15.0,
        help="Boost for names (entities, areas) sent by Home Assistant (0-20) "
        "(Default: 15.0)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=10.0,
        help="Seconds to wait for Google after the audio ends (Default: 10)",
    )
    parser.add_argument(
        "--credentials-file",
        default=os.environ.get("CREDENTIALS_FILE"),
        help=(
            "File containing Google STT credentials (e.g., credentials.json) "
            "(env: CREDENTIALS_FILE)"
        ),
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        default=_env_flag("DEBUG_LOGGING"),
        help="Log DEBUG messages (env: DEBUG_LOGGING)",
    )
    args = parser.parse_args()
    if not args.credentials_file:
        parser.error("--credentials-file (or CREDENTIALS_FILE) is required")
    return args


def build_info(model: str) -> Info:
    """Build the Wyoming info advertised to Home Assistant."""
    attribution = Attribution(name="Cheerpipe", url=REPOSITORY_URL)
    return Info(
        asr=[
            AsrProgram(
                name="google-stt",
                description="Google Cloud Speech-to-Text",
                attribution=attribution,
                version=__version__,
                installed=True,
                models=[
                    AsrModel(
                        name=model,
                        description=f"Google Cloud Speech-to-Text ({model})",
                        attribution=Attribution(
                            name="Google Cloud",
                            url="https://cloud.google.com/speech-to-text",
                        ),
                        version=None,
                        installed=True,
                        languages=supported_languages(),
                    )
                ],
            )
        ],
    )


async def main() -> None:
    """Start Wyoming Google STT server."""
    args = parse_arguments()

    logging.basicConfig(level=logging.DEBUG if args.debug else logging.INFO)
    _LOGGER.debug(args)

    if not os.path.exists(args.credentials_file):
        _LOGGER.error("Credentials file not found: %s", args.credentials_file)
        sys.exit(1)

    try:
        speech_config = SpeechConfig(
            language=args.language,
            alternative_languages=args.alternative_languages,
            model=args.model,
            single_utterance=args.single_utterance,
            phrases=args.phrases,
            phrase_boost=args.phrase_boost,
            names_boost=args.names_boost,
            timeout=args.timeout,
        )
    except ValidationError as err:
        _LOGGER.error("Invalid configuration: %s", err)
        sys.exit(1)

    _LOGGER.debug("Creating Google STT Transcriber")
    google_stt = GoogleSpeechTranscriberAsync(credentials_path=args.credentials_file)

    server = AsyncServer.from_uri(args.uri)
    _LOGGER.info(
        "Ready (model=%s, language=%s, alternatives=%s)",
        speech_config.model,
        speech_config.language,
        speech_config.alternative_languages,
    )

    # The Wyoming server stops gracefully on SIGTERM.
    await server.run(
        partial(
            GoogleEventHandler,
            google_stt,
            build_info(speech_config.model),
            speech_config,
        )
    )
    _LOGGER.info("Server shut down.")


def run() -> None:
    """Run the server until stopped."""
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    run()
