
---

# YaratelBot Project Documentation

**Author**: Nihan  
**Date**: April 12, 2025  
**Project**: YaratelBot - A Telegram Bot for Text and Voice Interaction

This document provides an overview of the development process for YaratelBot, a Telegram bot designed to handle text and voice messages using the Yarabot API. It covers the code structure, chat logging functionality, voice message handling, response cleaning, Dockerization of the application, and performance optimizations implemented during development.

---

## Project Overview

YaratelBot is a Telegram bot that interacts with users via text and voice messages, leveraging the Yarabot API (`https://backend.yarabot.ir`) for message processing. The bot was developed to:
- Respond to text messages using the Yarabot API.
- Process voice messages by sending them in OGG format to the Yarabot API for Speech-to-Text (STT) transcription (pending STT service activation by the backend admin).
- Log all chat interactions in a structured JSON file for record-keeping.
- Clean responses by removing unwanted asterisks (`*`) that were appearing in the Yarabot API output.
- Run in a Docker container on a virtual machine (VM) for consistent deployment.

The project was developed in Python, using the `python-telegram-bot` library for Telegram integration and `httpx` for API requests. The bot was Dockerized to ensure portability and ease of deployment on a Ubuntu-based VM.

---

## Code Structure and Explanation

The bot’s main code is contained in `newbot.py`, which consists of 353 lines (as verified by `wc -l newbot.py`). Below is an overview of the key components and their functionality.

### 1. Imports and Setup

```python
import httpx
import json
import logging
import os
from datetime import datetime
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    CallbackContext
)
```

- **Libraries Used**:
  - `httpx`: For making asynchronous HTTP requests to the Yarabot API.
  - `python-telegram-bot`: For interacting with the Telegram API (version 21.0.1).
  - `logging`, `json`, `os`, `datetime`: Standard Python libraries for logging, file handling, and timestamp generation.

- **Logging Setup**:
  The bot logs operational details to `bot_logs.log` for debugging purposes:

  ```python
  logging.basicConfig(
      level=logging.DEBUG,
      format='%(asctime)s - %(levelname)s - %(message)s',
      handlers=[
          logging.FileHandler("bot_logs.log"),
          logging.StreamHandler()
      ]
  )
  logger = logging.getLogger(__name__)
  ```

  Logs include timestamps, log levels (e.g., DEBUG, INFO, ERROR), and messages, written to both a file (`bot_logs.log`) and the console.

- **Constants**:
  The bot uses the following constants for configuration:

  ```python
  TELEGRAM_TOKEN = ''
  AGENT_ID = ''
  API_TOKEN = ''
  CHAT_API_URL = f'https://backend.yarabot.ir/agent/bot/{AGENT_ID}/chat'
  ```

  - `TELEGRAM_TOKEN`: The bot’s token, provided by BotFather, to authenticate with the Telegram API.
  - `AGENT_ID` and `API_TOKEN`: Credentials for the Yarabot API.
  - `CHAT_API_URL`: The endpoint for sending text and voice messages to the Yarabot API.

- **Directories and Files**:
  The bot creates directories for temporary files and chat logs:

  ```python
  TEMP_DIR = "temp_audio"
  CHAT_LOG_FILE = "chat_logs.json"
  ```

  - `TEMP_DIR`: Stores temporary OGG files downloaded from Telegram.
  - `CHAT_LOG_FILE`: Stores chat logs in JSON format.
  - **Note**: The `converted_wav_files` directory from the previous version was removed since WAV conversion is no longer required; the Yarabot API now accepts OGG files directly.

### 2. Main Functions

#### `start` Function
Handles the `/start` command, sending a welcome message to the user:

```python
async def start(update: Update, context: CallbackContext) -> None:
    """Send a welcome message when the /start command is issued."""
    chat_id = update.message.chat_id
    logger.info(f"Received /start command from chat ID: {chat_id}")
    welcome_message = "سلام ، من یارابات هستم ، دستیار هوش مصنوعی در خدمت شما"
    await update.message.reply_text(welcome_message)

    # Log the bot's response
    log_chat(chat_id, "text", welcome_message, "outgoing")
```

- Logs the command and the bot’s response.
- The welcome message was updated from "Hello! How can I assist you today? I can handle both text and voice messages!" to "سلام ، من یارابات هستم ، دستیار هوش مصنوعی در خدمت شما" (Hello, I am YaraBot, your AI assistant at your service) to better suit the Persian-speaking audience and reflect the bot’s identity.

#### `handle_text_message` Function
Processes incoming text messages:

```python
async def handle_text_message(update: Update, context: CallbackContext) -> None:
    """Send the user's text message to the Yarabot API and return its response."""
    user_message = update.message.text
    chat_id = update.message.chat_id
    logger.info(f"Received text message from chat ID {chat_id}: {user_message}")

    # Log the incoming user message
    log_chat(chat_id, "text", user_message, "incoming")

    # Retrieve the session ID for this chat, if it exists
    session_id = chat_sessions.get(chat_id)
    logger.debug(f"Session ID for chat {chat_id}: {session_id}")

    # Prepare the form data
    data = {
        'type': 'text',
        'text': user_message
    }
    if session_id:
        data['session_id'] = session_id

    # Set the authorization header
    headers = {
        'authorization': API_TOKEN
    }

    await send_to_yarabot(chat_id, data, headers, update)
```

- Logs the incoming message.
- Sends the message to the Yarabot API with the appropriate session ID (if available).
- Calls `send_to_yarabot` to handle the API request and response.

#### `handle_voice_message` Function
Processes incoming voice messages:

```python
async def handle_voice_message(update: Update, context: CallbackContext) -> None:
    """Handle voice messages by downloading and sending the OGG file to the Yarabot API."""
    chat_id = update.message.chat_id
    logger.info(f"Received voice message from chat ID {chat_id}")

    # Get the voice file from the update
    voice = update.message.voice
    if not voice:
        logger.warning("No voice file found in the message")
        await update.message.reply_text("Error: Could not process the voice message.")
        return

    # Log the incoming voice message (log the file ID for reference)
    log_chat(chat_id, "voice", f"Voice message with file_id: {voice.file_id}", "incoming")

    # Download the voice file (OGG format)
    ogg_filename = f"{voice.file_id}.ogg"
    ogg_path = os.path.join(TEMP_DIR, ogg_filename)
    files = None

    try:
        file = await context.bot.get_file(voice.file_id)
        logger.debug(f"Downloading voice file to {ogg_path}")
        await file.download_to_drive(ogg_path)

        # Check the OGG file size to ensure it's not empty
        ogg_size = os.path.getsize(ogg_path)
        logger.debug(f"OGG file size: {ogg_size} bytes")
        if ogg_size == 0:
            logger.error("Downloaded OGG file is empty")
            await update.message.reply_text("Error: Downloaded audio file is empty.")
            return

        # Retrieve the session ID for this chat, if it exists
        session_id = chat_sessions.get(chat_id)
        logger.debug(f"Session ID for chat {chat_id}: {session_id}")

        # Prepare the form data for the API
        data = {
            'type': 'voice'
        }
        if session_id:
            data['session_id'] = session_id

        # Prepare the file to send (OGG format)
        files = {
            'file': (ogg_filename, open(ogg_path, 'rb'), 'audio/ogg')
        }

        # Set the authorization header
        headers = {
            'authorization': API_TOKEN
        }

        # Send the OGG file to the Yarabot API
        await send_to_yarabot(chat_id, data, headers, update, files=files)

    except Exception as e:
        logger.error(f"Error processing voice message: {e}")
        await update.message.reply_text(f"Error processing voice message: {e}")
        # Log the error response
        log_chat(chat_id, "text", f"Error processing voice message: {e}", "outgoing")

    finally:
        # Clean up the OGG file
        if os.path.exists(ogg_path):
            os.remove(ogg_path)
            logger.debug(f"Deleted temporary OGG file: {ogg_path}")
        # Ensure the file object is closed
        if files and 'file' in files:
            files['file'][1].close()
```

- Logs the incoming voice message with its `file_id`.
- Downloads the OGG file from Telegram.
- Sends the OGG file directly to the Yarabot API (unlike the previous version, which converted to WAV).
- Cleans up the temporary OGG file after processing.
- **Note**: Voice message processing still fails due to the STT service not being enabled on the backend.

#### `send_to_yarabot` Function
Handles communication with the Yarabot API and cleans responses:

```python
async def send_to_yarabot(chat_id: int, data: dict, headers: dict, update: Update, files: dict = None) -> None:
    try:
        timeout = httpx.Timeout(10.0, read=30.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            if files:
                response = client.stream("POST", CHAT_API_URL, data=data, headers=headers, files=files)
            else:
                response = client.stream("POST", CHAT_API_URL, data=data, headers=headers)
            async with response as stream:
                if stream.status_code == 200:
                    full_response = ""
                    async for chunk in stream.aiter_text():
                        if not chunk.strip():
                            continue
                        chunk_data = json.loads(chunk.strip())
                        if "session_id" in chunk_data:
                            chat_sessions[chat_id] = chunk_data["session_id"]
                        elif "data" in chunk_data:
                            full_response += chunk_data["data"]
                        elif "message_id" in chunk_data:
                            if full_response:
                                cleaned_response = full_response.replace('*', '')
                                await update.message.reply_text(cleaned_response)
                                log_chat(chat_id, "text", cleaned_response, "outgoing")
                                if data.get('type') == 'voice':
                                    log_chat(chat_id, "voice_transcription", cleaned_response, "outgoing")
                            return
                        elif "error" in chunk_data:
                            await update.message.reply_text(f"API Error: {chunk_data['error']}")
                            log_chat(chat_id, "text", f"API Error: {chunk_data['error']}", "outgoing")
                            return
                    if full_response:
                        cleaned_response = full_response.replace('*', '')
                        await update.message.reply_text(cleaned_response)
                        log_chat(chat_id, "text", cleaned_response, "outgoing")
                        if data.get('type') == 'voice':
                            log_chat(chat_id, "voice_transcription", cleaned_response, "outgoing")
                else:
                    error_body = await stream.aread()
                    error_body = error_body.decode('utf-8') if error_body else "No error body received"
                    error_message = f"Error: {stream.status_code}"
                    if stream.status_code == 400:
                        error_message += f" - Bad Request: {error_body}"
                        if "User has no STT service enabled" in error_body:
                            error_message += "\nPlease enable STT service in the Yarabot API settings or contact support."
                    await update.message.reply_text(error_message)
                    log_chat(chat_id, "text", error_message, "outgoing")
    except httpx.ReadTimeout as e:
        await update.message.reply_text("Error: API response timed out. Please try again later.")
        log_chat(chat_id, "text", "Error: API response timed out. Please try again later.", "outgoing")
    except Exception as e:
        await update.message.reply_text(f"Error communicating with API: {e}")
        log_chat(chat_id, "text", f"Error communicating with API: {e}", "outgoing")
```

- Sends requests to the Yarabot API with appropriate headers and data.
- Handles streaming responses, accumulating message chunks.
- Cleans the response by removing all asterisks (`*`) using `cleaned_response = full_response.replace('*', '')`, addressing an issue where the Yarabot API was returning responses with unwanted asterisks (e.g., "**سلام** **من** **خوبم**").
- Sends the cleaned response to the user and logs it.
- Includes timeout handling to prevent hanging requests.

#### `main` Function
Sets up the bot and starts polling:

```python
def main() -> None:
    logger.info("Starting the Telegram bot...")
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))
    application.add_handler(MessageHandler(filters.VOICE, handle_voice_message))
    application.run_polling()
```

- Initializes the bot with the Telegram token.
- Registers handlers for the `/start` command, text messages, and voice messages.
- Starts polling to listen for incoming messages.

---

## Chat Logging Functionality

The bot logs all chat interactions (incoming and outgoing messages) to a `chat_logs.json` file. This functionality was implemented to keep a record of conversations for debugging, analysis, or future features like chat history retrieval.

### Implementation

The `log_chat` function handles logging:

```python
def log_chat(chat_id: int, message_type: str, content: str, direction: str) -> None:
    try:
        with open(CHAT_LOG_FILE, 'r') as f:
            logs = json.load(f)
        log_entry = {
            "chat_id": chat_id,
            "timestamp": datetime.utcnow().isoformat(),
            "message_type": message_type,
            "content": content,
            "direction": direction
        }
        logs.append(log_entry)
        with open(CHAT_LOG_FILE, 'w') as f:
            json.dump(logs, f, indent=4, ensure_ascii=False)
        logger.info(f"Logged {direction} message for chat ID {chat_id}: {content}")
    except Exception as e:
        logger.error(f"Error logging chat message: {e}")
```

- **Parameters**:
  - `chat_id`: The Telegram chat ID to identify the conversation.
  - `message_type`: The type of message (`text`, `voice`, or `voice_transcription`).
  - `content`: The message content (text or a description for voice messages).
  - `direction`: Indicates whether the message is `incoming` (from the user) or `outgoing` (from the bot).

- **Log Format**:
  Each log entry is a JSON object with the following fields:
  - `chat_id`: The chat ID.
  - `timestamp`: The UTC timestamp of the message.
  - `message_type`: The type of message.
  - `content`: The message content.
  - `direction`: The direction of the message.

- **Storage**:
  Logs are stored in `chat_logs.json` as a list of JSON objects. The file is initialized as an empty list if it doesn’t exist.

### Example Log Output

After a user sends a `/start` command and a text message, the `chat_logs.json` file might look like:

```json
[
    {
        "chat_id": 5018444479,
        "timestamp": "2025-04-12T12:00:00.123456",
        "message_type": "text",
        "content": "سلام ، من یارابات هستم ، دستیار هوش مصنوعی در خدمت شما",
        "direction": "outgoing"
    },
    {
        "chat_id": 5018444479,
        "timestamp": "2025-04-12T12:00:05.654321",
        "message_type": "text",
        "content": "سلام خوبی؟",
        "direction": "incoming"
    },
    {
        "chat_id": 5018444479,
        "timestamp": "2025-04-12T12:00:10.987654",
        "message_type": "text",
        "content": "سلام من خوبم تو چطور هستی",
        "direction": "outgoing"
    }
]
```

### Notes

- **Voice Messages**: Currently, voice messages are logged with their `file_id` (e.g., `"Voice message with file_id: 123456789"`). Once the STT service is enabled, the bot logs the transcribed text under `message_type: "voice_transcription"`.
- **Scalability**: The JSON file approach is suitable for small-scale logging. For production, a database (e.g., SQLite or PostgreSQL) would be more efficient for handling large volumes of logs and enabling querying.
- **Security**: Chat logs may contain sensitive user data. In a production environment, the `chat_logs.json` file should be secured with appropriate permissions (e.g., `chmod 666 chat_logs.json` for read/write access) or encryption.

---

## Voice Message Handling

The bot is designed to handle voice messages by sending them in OGG format to the Yarabot API for STT processing. However, the STT service is currently disabled on the backend, as indicated by the error `400 Bad Request: {"detail": "User has no STT service enabled"}`.

### Implementation

The `handle_voice_message` function (described above) performs the following steps:
1. **Download the Voice Message**:
   - Downloads the OGG file from Telegram using `context.bot.get_file(voice.file_id)`.
   - Saves it to `temp_audio/{file_id}.ogg`.

2. **Send to Yarabot API**:
   - Sends the OGG file directly to the Yarabot API with `type="voice"`.
   - Currently fails due to the STT service being disabled.

3. **Cleanup**:
   - Deletes the temporary OGG file after processing to save disk space.

### Changes from Previous Version

- **Removed WAV Conversion**:
  - The previous version converted OGG files to WAV using `pydub` because the Yarabot API initially required WAV format.
  - The API now accepts OGG files directly, so `pydub` and `ffmpeg` dependencies were removed, simplifying the process and reducing the container image size.
  - The `converted_wav_files` directory is no longer used, and WAV files are not preserved for testing.

### Current Status

- The voice message handling is partially functional:
  - The bot successfully downloads voice messages and sends them to the Yarabot API in OGG format.
  - However, the API request fails because the STT service is not enabled.
- Nihan has contacted the backend admin to enable the STT service, which will allow full voice message processing once activated.

---

## Response Cleaning (Asterisk Removal)

An issue was identified where the Yarabot API’s responses contained unwanted asterisks (`*`), likely used for markdown-style formatting (e.g., `**سلام** **من** **خوبم**`). These asterisks were displayed as literal characters in Telegram, cluttering the response. The bot was updated to clean these responses before sending them to the user.

### Implementation

The `send_to_yarabot` function was modified to include a cleaning step:

```python
if full_response:
    cleaned_response = full_response.replace('*', '')
    await update.message.reply_text(cleaned_response)
    log_chat(chat_id, "text", cleaned_response, "outgoing")
```

- **Cleaning Process**:
  - After accumulating the full response (`full_response`) from the Yarabot API, the bot removes all asterisks using `replace('*', '')`.
  - The cleaned response (`cleaned_response`) is then sent to the user and logged.

- **Example**:
  - **Before Cleaning**: `**سلام** **من** **خوبم** **تو** **چطور** **هستی**`
  - **After Cleaning**: `سلام من خوبم تو چطور هستی`

### Impact

- This fix ensures that responses are clean and readable for users.
- The cleaned responses are also logged in `chat_logs.json`, maintaining consistency between what the user sees and what is recorded.

---

## Dockerizing the Application

To ensure consistent deployment and portability, the bot was Dockerized and deployed on Nihan’s Ubuntu-based VM. Below are the steps taken to Dockerize the application.

### 1. Install Docker on Ubuntu

Docker was installed on the Ubuntu VM using the official Docker repository method:

```bash
sudo apt update
sudo apt install -y apt-transport-https ca-certificates curl software-properties-common
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo systemctl start docker
sudo systemctl enable docker
sudo usermod -aG docker $USER
```

- This installed the latest stable version of Docker Engine (likely 27.x as of April 2025).
- The user was added to the `docker` group to run Docker commands without `sudo`.

### 2. Create the `Dockerfile`

A `Dockerfile` was created to define the container image:

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["python", "newbot.py"]
```

- **Base Image**: `python:3.11-slim` was chosen for a lightweight Python environment.
- **Dependencies**:
  - Python dependencies were installed from `requirements.txt`.
  - **Note**: The previous version included `ffmpeg` for WAV conversion, but since the bot now sends OGG files directly, `ffmpeg` is no longer required.
- **Working Directory**: Set to `/app` to organize the application files.
- **Command**: Runs `python newbot.py` to start the bot.

### 3. Create `requirements.txt`

The `requirements.txt` file lists the Python dependencies:

```plaintext
httpx==0.27.0
python-telegram-bot==21.0.1
```

- **Changes**:
  - Removed `pydub==0.25.1` since WAV conversion is no longer needed.
  - Kept `httpx` and `python-telegram-bot` for API requests and Telegram integration.

### 4. Create `.dockerignore`

A `.dockerignore` file was created to exclude unnecessary files from the container image:

```plaintext
__pycache__
*.pyc
*.pyo
*.pyd
.Python
env/
venv/
.git
.gitignore
*.log
temp_audio/
chat_logs.json
```

- **Changes**:
  - Removed `converted_wav_files/` from the `.dockerignore` list since the directory is no longer used.
- This keeps the image lightweight by excluding temporary files, logs, and virtual environments.

### 5. Build and Run the Container

The container was built and run on Nihan’s VM:

```bash
docker build -t yaratelbot .
docker run -d --name yaratelbot_container -v $(pwd)/chat_logs.json:/app/chat_logs.json yaratelbot
```

- **Build**: The image was named `yaratelbot`.
- **Run**:
  - The container was named `yaratelbot_container`.
  - Volume mounts were used to persist `chat_logs.json` on the host.
  - The container runs in detached mode (`-d`).
- **Changes**:
  - Removed the volume mount for `converted_wav_files` since it’s no longer needed.

### 6. Verify the Mounts

The mounting points were verified to ensure the bot can read/write to the expected locations:
- `chat_logs.json` is mounted to `/app/chat_logs.json`, matching the bot’s `CHAT_LOG_FILE`.

Nihan can test the bot by sending messages and checking the mounted file:

```bash
cat chat_logs.json
```

### 7. Handle Container Name Conflicts

If the container name `yaratelbot_container` is already in use, Nihan encountered a conflict error:

```
docker: Error response from daemon: Conflict. The container name "/yaratelbot_container" is already in use by container "a757d3cdca16a062d008752640370b2631e7f53a9b3e641e776f7d79425d1b3d". You have to remove (or rename) that container to be able to reuse that name.
```

To resolve this, the existing container was stopped and removed:

```bash
docker stop yaratelbot_container
docker rm yaratelbot_container
docker run -d --name yaratelbot_container -v $(pwd)/chat_logs.json:/app/chat_logs.json yaratelbot
```

---

## Performance Optimizations

Several steps were taken to make the bot fast and efficient:

### 1. Lightweight Base Image
- Used `python:3.11-slim` as the base image instead of the full `python:3.11` image.
- The `slim` variant reduces the image size by excluding unnecessary tools and libraries, resulting in faster build times and lower resource usage.
- The final image size is approximately 120-150 MB (smaller than the previous 150-200 MB due to the removal of `ffmpeg` and `pydub`).

### 2. Efficient Dependency Installation
- Used `pip install --no-cache-dir` in the `Dockerfile` to avoid caching Python packages, reducing the image size:

  ```dockerfile
  RUN pip install --no-cache-dir -r requirements.txt
  ```

- Pinned specific versions in `requirements.txt` (e.g., `httpx==0.27.0`) to ensure consistent behavior and avoid unexpected updates.

### 3. Removed WAV Conversion
- The previous version converted OGG files to WAV, requiring `pydub` and `ffmpeg`.
- The updated bot sends OGG files directly to the Yarabot API, eliminating the need for conversion, reducing processing time, and removing dependencies (`pydub` and `ffmpeg`).
- This also reduced disk usage by removing the need to store WAV files.

### 4. Timeout Handling for API Requests
- Added timeout settings to prevent the bot from hanging on slow API responses:

  ```python
  timeout = httpx.Timeout(10.0, read=30.0)
  ```

  - Connect timeout: 10 seconds.
  - Read timeout: 30 seconds.
- This ensures the bot remains responsive even if the Yarabot API is slow or unresponsive.

### 5. Streaming Response Handling
- The Yarabot API returns streaming responses, which the bot processes efficiently by:
  - Accumulating chunks incrementally (`full_response += chunk_data["data"]`).
  - Sending the response to the user only when complete, reducing unnecessary Telegram API calls.
- Fixed a previous issue with streaming responses (`Attempted to access streaming response content, without having called read()`) by properly reading the response body for non-200 status codes:

  ```python
  error_body = await stream.aread()
  ```

### 6. Lightweight Logging
- The chat logging function (`log_chat`) uses a JSON file, which is lightweight for small-scale use.
- File operations are minimized by reading and writing the entire log file only when a new message is logged, avoiding frequent disk I/O.

### 7. Excluded Unnecessary Files
- The `.dockerignore` file excludes unnecessary files (e.g., logs, temporary files) from the container image, reducing build time and image size.

---

## Conclusion

The YaratelBot project, led by Nihan, has successfully implemented a Telegram bot with the following features:
- Text and voice message handling (voice processing pending STT activation).
- Chat logging in a structured JSON file.
- Response cleaning to remove unwanted asterisks from Yarabot API responses.
- Deployment in a Docker container on a Ubuntu VM.

The bot is optimized for performance with a lightweight image, efficient dependency management, simplified voice message handling, and robust error handling. Once the STT service is enabled by the backend admin, voice message processing will be fully functional, and Nihan can proceed with additional features like group chat or WhatsApp integration.

---

## Next Steps

1. **Enable STT Service**:
   - Await confirmation from the backend admin that the STT service is enabled.
   - Test voice message processing and update the chat logs to include transcribed text.

2. **Enhance Chat Logging**:
   - Consider switching to a database (e.g., SQLite) for scalability.
   - Add features like log querying or chat history retrieval.

3. **Further Features**:
   - Implement group chat functionality for the Telegram bot.
   - Proceed with WhatsApp bot integration, as outlined in Nihan’s task list.

4. **Security Improvements**:
   - Run the container as a non-root user.
   - Secure the `chat_logs.json` file with appropriate permissions or encryption.

---

**Prepared by**: Nihan  
**Date**: April 12, 2025
```
