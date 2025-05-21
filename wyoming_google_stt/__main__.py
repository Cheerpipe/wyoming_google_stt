import argparse  # noqa: D100
import asyncio
import logging
import contextlib
import os
import signal
import re
from functools import partial

from wyoming.info import AsrModel, AsrProgram, Attribution, Info
from wyoming.server import AsyncServer
#from .google_stt import GoogleSpeechTranscriber
from .google_stt import GoogleSpeechTranscriberAsync
from .handler import GoogleEventHandler
from .version import __version__
from . import SpeechConfig

_LOGGER = logging.getLogger(__name__)

stop_event = asyncio.Event()

def handle_stop_signal(*args):
    """Handle shutdown signal and set the stop event."""
    _LOGGER.info("Received stop signal. Shutting down...")
    stop_event.set()
    exit(0)

def parse_arguments():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--uri", default="tcp://0.0.0.0:10300", help="unix:// or tcp://"
    )
    parser.add_argument(
        "--language",
        default="es-US",
        help="List of languages to set for transcription (e.g., en-US fr-FR es-ES) (Default=es-US)"
    )
    parser.add_argument(
        "--alternative-languages",
        nargs="+",
        default=["en-US"],
        help="List of secondary languages to set for transcription (e.g., en-US fr-FR es-ES) (Default=en-US)"
    )    
    parser.add_argument(
        "--model",
        default="latest_short",
        help="Model name (e.g., llatest_long, latest_short, command_and_search, phone_call, video, default. (Default=latest_short)"
    )    
    parser.add_argument(
        "--credentials-file",
        required=True,
        help="File containing Google STT credentials (e.g., /path/to/credentials.json)"
    )      
    parser.add_argument("--debug", action="store_true", help="Log DEBUG messages")
    return parser.parse_args()


async def main() -> None:
    """Start Wyoming Microsoft STT server."""
    args = parse_arguments()
    # Todo: Add arguents validations
    _LOGGER.debug("Arguments parsed successfully.")

    speech_config = SpeechConfig(
        language=args.language,
        alternative_languages=args.alternative_languages,
        model=args.model
    )

    # Set up logging
    logging.basicConfig(level=logging.DEBUG if args.debug else logging.INFO)
    _LOGGER.debug("Arguments parsed successfully.")

    wyoming_info = Info(
        asr=[
            AsrProgram(
                name="Google Speech Recognition",
                description="Google Speech Recognition",
                attribution=Attribution(
                    name="Cheerpipe",
                    url="https://github.com/hugobloem/wyoming-google-stt/",
                ),
                version=__version__,
                installed=True,
                models=[
                    AsrModel(
                        name="Google Speech Recognition",
                        description="Google Speech Recognition",
                        attribution=Attribution(
                            name="Cheerpipe",
                            url="https://github.com/hugobloem/wyoming-google-stt/",
                        ),
                        version=__version__,
                        installed=True,
                        languages=[args.language],
                    )
                ],
            )
        ],
    )
    _LOGGER.debug("Setting credential file path.")
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = args.credentials_file

    _LOGGER.debug("Creating Google STT Transcriber")
    google_stt = GoogleSpeechTranscriberAsync()  # Usará GOOGLE_APPLICATION_CREDENTIALS    

    # # Test Google STT conection
    # _LOGGER.debug("Testing Google Cloud connection.")
    # transcriber = GoogleSpeechTranscriber()
    # success = transcriber.test_connection()
    # if success:
    #     _LOGGER.debug("Connection to Google STT service successfully.")
    # else:
    #     _LOGGER.error("Can't connect to Google STT service. Please check your credentials.")

    # Initialize server and run
    _LOGGER.debug("Initializing server.")
    server = AsyncServer.from_uri(args.uri)
    _LOGGER.info("Ready")
    model_lock = asyncio.Lock()
    try:
        await server.run(
            partial(
                GoogleEventHandler,
                google_stt,
                wyoming_info,
                speech_config,
                model_lock,
            )
        )
    except Exception as e:
        _LOGGER.error(f"An error occurred while running the server: {e}")


if __name__ == "__main__":
    # Set up signal handling for graceful shutdown
    signal.signal(signal.SIGTERM, handle_stop_signal)
    signal.signal(signal.SIGINT, handle_stop_signal)

    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(main())
