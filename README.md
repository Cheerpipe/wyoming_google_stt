# Wyoming Google Speech-to-Text

## What is this

This is a **Wyoming protocol server** for [Google Cloud Speech-to-Text](https://cloud.google.com/speech-to-text).

It functions as a **Speech-to-Text (STT) component** designed to be used by **Home Assistant**. It allows **Assist** to recognize voice commands, transforming audio into text so it can subsequently be processed as **intents** to execute actions. It supports **streaming transcription**, allowing for low-latency response times, and includes support for phrase boosting (speech contexts) to improve accuracy for specific commands.

## How it works

1.  **Audio Stream:** The client (e.g., Home Assistant Assist) sends audio chunks to this server via the Wyoming protocol.
2.  **Cloud Processing:** This server authenticates with Google Cloud using your Service Account credentials and streams the audio asynchronously to the Google Speech-to-Text API.
3.  **Transcription:** Google processes the audio in real-time using its advanced ML models.
4.  **Result:** The transcribed text is returned to this server, which delivers it to the Wyoming client as a finalized transcript to be processed as an intent.

## Prerequisites

* **Google Cloud Platform (GCP) Account**
* **Service Account JSON Key** (created below)
* **Docker**
* **Docker Compose**

---

### 🔑 Generating Google Cloud Credentials (Service Account JSON)

To enable cloud speech recognition, you must configure a Google Cloud project and generate a Service Account JSON key. **Note:** Google requires a billing account to be enabled on your project, even if your usage falls within the free usage tier.

1.  **Set up GCP Project & Billing:**
    * Open the [Google Cloud Console](https://console.cloud.google.com/).
    * Create a new project or select an existing one.
    * **Crucially, enable billing** for the chosen project.

2.  **Enable the Speech-to-Text API:**
    * In the GCP Console, navigate to the **APIs & Services** dashboard.
    * Search for **"Cloud Speech-to-Text API"** and click the **ENABLE** button.

3.  **Create a Service Account:**
    * Go to the **IAM & Admin** > **Service Accounts** section.
    * Click **CREATE SERVICE ACCOUNT**.
    * Provide a clear **Service Account Name** (e.g., `wyoming-stt-access`) and description.
    * Grant it only the **Cloud Speech Client** role (`roles/speech.client`), then click **DONE**.

4.  **Generate and Download the Key File:**
    * From the same **IAM & Admin** > **Service Accounts** page, click the name of the Service Account you just created.
    * Navigate to the **KEYS** tab and select **ADD KEY** > **Create new key**.
    * Choose **JSON** as the key type and click **CREATE**.
5.  **Finalize:** **Rename the downloaded file to `credentials.json`** and place it in the root directory where your `docker-compose.yaml` file is located. This file is required by the `Volumes` configuration.

---

## Quick Start

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/Cheerpipe/wyoming_google_stt.git
    cd wyoming_google_stt
    ```
2.  **Configure:** Edit `docker-compose.yaml` to set the environment variables and options you need (see sections below).
3.  **Build and run the container:**
    ```bash
    docker compose up -d --build
    ```
    (Use `-d` for detached execution.)
4.  **Add it to Home Assistant:** *Settings* > *Devices & services* > *Add integration* > *Wyoming Protocol*, using the host of the container and port `10300`.

---

## Volumes

The server requires a volume mount for the Google Cloud credentials file.

| Path (Inside Container) | Description | Recommended Host Mount Example |
| :--- | :--- | :--- |
| **/data/credentials.json** | **REQUIRED.** The JSON file containing your Google Cloud Service Account keys. Mount it read-only. | `./credentials.json:/data/credentials.json:ro` |

---

## Configuration (Environment Variables)

You can configure the service using environment variables in your `docker-compose.yaml`.

| Variable | Description | Default / Example |
| :--- | :--- | :--- |
| **CREDENTIALS_FILE** | **REQUIRED.** Path to the credentials JSON file inside the container. | `/data/credentials.json` |
| **DEBUG_LOGGING** | Set to `TRUE` to enable debug-level logging output. | `FALSE` |
| **LANGUAGE** | Primary language. | `es-US` |
| **ALTERNATIVE_LANGUAGES** | Up to 3 secondary languages, separated by spaces. Empty to disable. | `en-US` |
| **MODEL** | Google STT v1 model. `latest_short` or `command_and_search` are best for voice commands. | `latest_short` |
| **DISABLE_SINGLE_UTTERANCE** | Set to `TRUE` to keep listening after the first utterance. | `FALSE` |

## Configuration (Command-Line Options)

Every option can also be passed as an argument (`command:` in `docker-compose.yaml`). Arguments override environment variables.

| Option | Description | Default |
| :--- | :--- | :--- |
| `--credentials-file` | Path to the credentials JSON file. | `CREDENTIALS_FILE` |
| `--language` | Primary language. | `es-US` |
| `--alternative-languages` | Up to 3 secondary languages. | `en-US` |
| `--model` | Recognition model. | `latest_short` |
| `--single-utterance` / `--no-single-utterance` | Stop recognition (and audio upload) after the first utterance. If the model rejects it, the server retries without it. | enabled |
| `--phrases` | Phrases to boost (e.g. `'enciende la luz' 'apaga la luz'`). | none |
| `--phrase-boost` | Boost (0-20) for `--phrases` and terms sent by Home Assistant. High values cause false positives. | `10` |
| `--names-boost` | Boost (0-20) for names (entities, areas) sent by Home Assistant. | `15` |
| `--timeout` | Seconds to wait for Google after the audio ends. | `10` |
| `--uri` | Address to listen on. | `tcp://0.0.0.0:10300` |
| `--debug` | Log debug messages. | `DEBUG_LOGGING` |

### Language handling

* If Home Assistant asks for a language, it becomes the primary one and the configured languages are used as alternatives. Generic codes such as `es` are mapped to the configured variant (e.g. `es-US`).
* The language detected by Google is returned to Home Assistant with the transcript.

### Phrase boosting

Besides `--phrases`, the names and terms that Home Assistant sends with each request (`transcript_names` and `transcript_terms`, Wyoming 1.10+) are boosted automatically.

---

## Staying within the free tier

Google STT **v1** includes 60 free minutes per month (billed per second, rounded per request); this server uses v1 for that reason. To avoid surprises:

* Keep `--single-utterance` enabled: audio stops being uploaded as soon as Google detects the end of the command.
* Each transcription logs the seconds of audio sent (`Transcription completed (3.2s of audio sent ...)`).
* Budget alerts only notify you. For a hard limit, lower the Speech-to-Text API request quotas in *IAM & Admin* > *Quotas*.

---

## Credits and Acknowledgments

A special thank you to **sdetweil** for creating and sharing the repository: [https://github.com/sdetweil/wyoming-google](https://github.com/sdetweil/wyoming-google). Your work provided the foundation and necessary inspiration for building this Wyoming STT component.
