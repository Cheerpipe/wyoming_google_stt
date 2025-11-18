"""Wyoming server for Google STT."""
import argparse
import asyncio
import contextlib
import logging
import os
import signal
from functools import partial

from wyoming.info import AsrModel, AsrProgram, Attribution, Info
from wyoming.server import AsyncServer

from . import SpeechConfig
from .google_stt import GoogleSpeechTranscriberAsync
from .handler import GoogleEventHandler
from .version import __version__

_LOGGER = logging.getLogger(__name__)

stop_event = asyncio.Event()


def handle_stop_signal(*args):
    """Handle shutdown signal and set the stop event."""
    _LOGGER.info("Received stop signal (SIGTERM). Shutting down...")
    stop_event.set()


def parse_arguments():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--uri", default="tcp://0.0.0.0:10300", help="unix:// or tcp://"
    )
    parser.add_argument(
        "--language",
        default="es-US",
        help=(
            "Primary language for transcription (e.g., en-US, es-ES) "
            "(Default: es-US)"
        ),
    )
    parser.add_argument(
        "--alternative-languages",
        nargs="+",
        default=["en-US"],
        help=(
            "List of secondary languages for transcription "
            "(e.g., en-US fr-FR) (Default: en-US)"
        ),
    )
    parser.add_argument(
        "--model",
        default="latest_short",
        help=(
            "Model name (e.g., latest_long, latest_short, command_and_search) "
            "(Default: latest_short)"
        ),
    )
    parser.add_argument(
        "--phrases",
        nargs="+",
        default=[],
        help=(
            "Phrases to boost with SpeechContext "
            "(e.g., 'turn on the light' 'turn off the fan')"
        ),
    )
    parser.add_argument(
        "--phrase-boost",
        type=float,
        default=20.0,
        help="Strength of phrase boost (0-20) (Default: 20.0)",
    )
    parser.add_argument(
        "--credentials-file",
        required=True,
        help="File containing Google STT credentials (e.g., credentials.json)",
    )
    parser.add_argument("--debug", action="store_true", help="Log DEBUG messages")
    return parser.parse_args()


async def main() -> None:
    """Start Wyoming Google STT server."""
    args = parse_arguments()
    _LOGGER.debug(args)

    if not os.path.exists(args.credentials_file):
        _LOGGER.error("Credentials file not found: %s", args.credentials_file)
        exit(1)

    speech_config = SpeechConfig(
        language=args.language,
        alternative_languages=args.alternative_languages,
        model=args.model,
        phrases=args.phrases,
        phrase_boost=args.phrase_boost,
    )

    # Set up logging
    logging.basicConfig(level=logging.DEBUG if args.debug else logging.INFO)

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

    _LOGGER.debug("Creating Google STT Transcriber")
    google_stt = GoogleSpeechTranscriberAsync(
        credentials_path=args.credentials_file
    )

    # Initialize server and run
    _LOGGER.debug("Initializing server.")
    server = AsyncServer.from_uri(args.uri)
    _LOGGER.info("Ready")

    server_task = None
    try:
        server_task = asyncio.create_task(
            server.run(
                partial(
                    GoogleEventHandler,
                    google_stt,
                    wyoming_info,
                    speech_config,
                )
            )
        )

        # Wait for either the server task to finish, or the stop_event
        # (from SIGTERM) to be set.
        stop_wait_task = asyncio.create_task(stop_event.wait())

        done, pending = await asyncio.wait(
            [server_task, stop_wait_task],
            return_when=asyncio.FIRST_COMPLETED,
        )

        for task in pending:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    except asyncio.CancelledError:
        # This is the expected path for Ctrl+C (SIGINT)
        _LOGGER.info("Server cancelled (SIGINT). Shutting down.")

    except Exception:
        _LOGGER.exception("An error occurred while running the server")

    finally:
        # Ensure the server task is always cleaned up
        if server_task and not server_task.done():
            _LOGGER.debug("Cleaning up server task...")
            server_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await server_task
        _LOGGER.info("Server shut down.")


if __name__ == "__main__":
    # We only handle SIGTERM.
    # We let asyncio.run() handle SIGINT (KeyboardInterrupt) by default.
    signal.signal(signal.SIGTERM, handle_stop_signal)

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        # This block will now correctly catch the Ctrl+C
        _LOGGER.debug("KeyboardInterrupt caught, shutting down.")