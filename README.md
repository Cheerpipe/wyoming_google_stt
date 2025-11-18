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
    * Provide a clear **Service Account Name** (e.g., `wyoming-stt-access`) and description, then click **DONE**.

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
2.  **Build the container image:**
    ```bash
    bash scripts/build.sh
    ```
3.  **Configure:** Edit the `docker-compose.yaml` file to set your **required** environment variables (`DEBUG_LOGGING` AND `CREDENTIALS_FILE`) and volume paths (see sections below).
4.  **Run the container:**
    ```bash
    docker compose up -d
    ```
    (Use `-d` for detached execution.)

---

## Volumes

The server requires a volume mount for the Google Cloud credentials file.

| Path (Inside Container) | Description | Recommended Host Mount Example |
| :--- | :--- | :--- |
| **/data/credentials.json** | **REQUIRED.** The JSON file containing your Google Cloud Service Account keys. | `./credentials.json` |

---

## Configuration (Environment Variables)

You can configure the service using environment variables in your `docker-compose.yaml`.

| Variable | Description | Default / Example |
| :--- | :--- | :--- |
| **CREDENTIALS_FILE** | **REQUIRED.** Path to the credentials JSON file inside the container. | `/data/credentials.json` |
| **DEBUG_LOGGING** | Set to `TRUE` to enable debug-level logging output. | `FALSE` |

---

## Credits and Acknowledgments

A special thank you to **sdetweil** for creating and sharing the repository: [https://github.com/sdetweil/wyoming-google](https://github.com/sdetweil/wyoming-google). Your work provided the foundation and necessary inspiration for building this Wyoming STT component.
