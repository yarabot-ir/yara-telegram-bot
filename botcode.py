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

# Set up logging to write to a file
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("bot_logs.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Credentials and endpoint settings
TELEGRAM_TOKEN = ''
AGENT_ID = ''
API_TOKEN = ''

# API endpoint
CHAT_API_URL = f'https://backend.yarabot.ir/agent/bot/{AGENT_ID}/chat'

# Directory to store temporary audio files
TEMP_DIR = "temp_audio"
if not os.path.exists(TEMP_DIR):
    os.makedirs(TEMP_DIR)

# File to store chat logs
CHAT_LOG_FILE = "chat_logs.json"
if not os.path.exists(CHAT_LOG_FILE):
    with open(CHAT_LOG_FILE, 'w') as f:
        json.dump([], f)  # Initialize with an empty list

# Dictionary to store session IDs per chat
chat_sessions = {}

def log_chat(chat_id: int, message_type: str, content: str, direction: str) -> None:
    """Log a chat message to the chat_logs.json file."""
    try:
        # Read existing logs
        with open(CHAT_LOG_FILE, 'r') as f:
            logs = json.load(f)

        # Create new log entry
        log_entry = {
            "chat_id": chat_id,
            "timestamp": datetime.utcnow().isoformat(),
            "message_type": message_type,
            "content": content,
            "direction": direction  # "incoming" for user messages, "outgoing" for bot responses
        }

        # Append new log entry
        logs.append(log_entry)

        # Write back to file
        with open(CHAT_LOG_FILE, 'w') as f:
            json.dump(logs, f, indent=4, ensure_ascii=False)

        logger.info(f"Logged {direction} message for chat ID {chat_id}: {content}")
    except Exception as e:
        logger.error(f"Error logging chat message: {e}")

async def start(update: Update, context: CallbackContext) -> None:
    """Send a welcome message when the /start command is issued."""
    chat_id = update.message.chat_id
    logger.info(f"Received /start command from chat ID: {chat_id}")
    welcome_message = "سلام ، من یارابات هستم ، دستیار هوش مصنوعی در خدمت شما"
    await update.message.reply_text(welcome_message)

    # Log the bot's response
    log_chat(chat_id, "text", welcome_message, "outgoing")

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

        # Log the request details
        logger.debug(f"Sending voice request to API: {CHAT_API_URL}")
        logger.debug(f"Headers: {headers}")
        logger.debug(f"Data: {data}")
        logger.debug(f"Files: {list(files.keys())}")

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

async def send_to_yarabot(chat_id: int, data: dict, headers: dict, update: Update, files: dict = None) -> None:
    """Send a request to the Yarabot API and handle the streaming response."""
    try:
        # Increase timeout for streaming responses
        timeout = httpx.Timeout(10.0, read=30.0)  # 10s for connect, 30s for read
        async with httpx.AsyncClient(timeout=timeout) as client:
            logger.debug(f"Sending request to API: {CHAT_API_URL} with data: {data}")
            if files:
                response = client.stream("POST", CHAT_API_URL, data=data, headers=headers, files=files)
            else:
                response = client.stream("POST", CHAT_API_URL, data=data, headers=headers)

            async with response as stream:
                if stream.status_code == 200:
                    full_response = ""

                    async for chunk in stream.aiter_text():
                        logger.debug(f"Received chunk: {chunk}")
                        if not chunk.strip():
                            logger.debug("Skipping empty chunk")
                            continue

                        try:
                            chunk_data = json.loads(chunk.strip())
                            if isinstance(chunk_data, dict):
                                if "session_id" in chunk_data:
                                    chat_sessions[chat_id] = chunk_data["session_id"]
                                    logger.debug(f"Stored session_id: {chunk_data['session_id']}")
                                elif "data" in chunk_data:
                                    full_response += chunk_data["data"]
                                elif "message_id" in chunk_data:
                                    logger.debug(f"Received message_id: {chunk_data['message_id']}, ending stream")
                                    if full_response:
                                        # Clean the response by removing all asterisks
                                        cleaned_response = full_response.replace('*', '')
                                        logger.info(f"Sending cleaned response to user: {cleaned_response}")
                                        await update.message.reply_text(cleaned_response)
                                        # Log the cleaned bot's response
                                        log_chat(chat_id, "text", cleaned_response, "outgoing")
                                        # If this is a voice message response, log the transcribed text
                                        if data.get('type') == 'voice':
                                            log_chat(chat_id, "voice_transcription", cleaned_response, "outgoing")
                                    else:
                                        logger.warning("No response accumulated before message_id")
                                        await update.message.reply_text("No response received from the API.")
                                        # Log the error response
                                        log_chat(chat_id, "text", "No response received from the API.", "outgoing")
                                    return
                                elif "error" in chunk_data:
                                    logger.warning(f"API returned an error: {chunk_data['error']}")
                                    await update.message.reply_text(f"API Error: {chunk_data['error']}")
                                    # Log the error response
                                    log_chat(chat_id, "text", f"API Error: {chunk_data['error']}", "outgoing")
                                    return
                                else:
                                    logger.warning(f"Unexpected JSON structure: {chunk_data}")
                                    await update.message.reply_text("Received unexpected response format from API.")
                                    # Log the error response
                                    log_chat(chat_id, "text", "Received unexpected response format from API.", "outgoing")
                                    return
                            else:
                                logger.warning(f"Chunk is not a dictionary: {chunk_data}")
                                await update.message.reply_text("Received unexpected response format from API.")
                                # Log the error response
                                log_chat(chat_id, "text", "Received unexpected response format from API.", "outgoing")
                                return

                        except json.JSONDecodeError as e:
                            logger.error(f"JSON decode error: {e} - Chunk: {chunk}")
                            await update.message.reply_text("Error: Could not parse API response.")
                            # Log the error response
                            log_chat(chat_id, "text", "Error: Could not parse API response.", "outgoing")
                            return
                        except Exception as e:
                            logger.error(f"Error processing chunk: {e} - Chunk: {chunk}")
                            await update.message.reply_text(f"Error processing API response: {e}")
                            # Log the error response
                            log_chat(chat_id, "text", f"Error processing API response: {e}", "outgoing")
                            return

                    logger.warning("Stream ended without a message_id chunk")
                    if full_response:
                        # Clean the response by removing all asterisks
                        cleaned_response = full_response.replace('*', '')
                        logger.info(f"Sending cleaned response to user: {cleaned_response}")
                        await update.message.reply_text(cleaned_response)
                        # Log the cleaned bot's response
                        log_chat(chat_id, "text", cleaned_response, "outgoing")
                        # If this is a voice message response, log the transcribed text
                        if data.get('type') == 'voice':
                            log_chat(chat_id, "voice_transcription", cleaned_response, "outgoing")
                    else:
                        logger.warning("No response received from the API")
                        await update.message.reply_text("No response received from the API.")
                        # Log the error response
                        log_chat(chat_id, "text", "No response received from the API.", "outgoing")

                else:
                    # Read the response body for non-200 status codes
                    error_body = await stream.aread()  # Use aread() to read the streaming response
                    error_body = error_body.decode('utf-8') if error_body else "No error body received"
                    logger.error(f"API error response body: {error_body}")
                    error_message = f"Error: {stream.status_code}"
                    if stream.status_code == 400:
                        error_message += f" - Bad Request: {error_body}"
                    elif stream.status_code == 401:
                        error_message += " - Unauthorized: Invalid API key."
                    elif stream.status_code == 404:
                        error_message += " - Not Found: Agent ID not found."
                    elif stream.status_code == 413:
                        error_message += " - Payload Too Large."
                    elif stream.status_code == 422:
                        error_message += " - Unprocessable Entity: Invalid data format."
                    else:
                        error_message += f" - {error_body}"
                    logger.error(f"HTTP error: {error_message}")
                    await update.message.reply_text(error_message)
                    # Log the error response
                    log_chat(chat_id, "text", error_message, "outgoing")

    except httpx.ReadTimeout as e:
        logger.error(f"Read timeout while communicating with API: {e}")
        await update.message.reply_text("Error: API response timed out. Please try again later.")
        # Log the error response
        log_chat(chat_id, "text", "Error: API response timed out. Please try again later.", "outgoing")
    except Exception as e:
        logger.error(f"Error communicating with API: {e}")
        await update.message.reply_text(f"Error communicating with API: {e}")
        # Log the error response
        log_chat(chat_id, "text", f"Error communicating with API: {e}", "outgoing")

def main() -> None:
    """Run the bot."""
    logger.info("Starting the Telegram bot...")
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    # Add handlers for /start command, text messages, and voice messages
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))
    application.add_handler(MessageHandler(filters.VOICE, handle_voice_message))

    # Start the bot with polling
    application.run_polling()

if __name__ == '__main__':
    main()