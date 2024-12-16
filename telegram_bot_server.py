import os
import tempfile
import logging
import asyncio
import json
from typing import Dict, Set, Optional
from dataclasses import dataclass
import time
from queue import Queue
import threading
from urllib.parse import urlparse
from dotenv import load_dotenv

from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

# Import our transcription functions
from transcriber import (
    transcribe_audio, cleanup_temp_files,
    is_youtube_url, download_youtube_video,
    is_google_drive_url, get_drive_file_id, download_from_google_drive
)

load_dotenv()

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Configuration
CONFIG = {
    'max_parallel_tasks': 3,
    'telegram_token': os.getenv('TELEGRAM_BOT_TOKEN'),
    'whitelist_file': 'whitelist.json',
    'temp_dir': 'temp_files',
    'supported_formats': {'.mp3', '.mp4', '.mpeg', '.mpga', '.m4a', '.wav', '.webm'}
}

ALL_USERS = -1

@dataclass
class TranscriptionTask:
    chat_id: int
    file_path: str
    is_url: bool = False
    task_id: Optional[str] = None

class TranscriptionQueue:
    def __init__(self, bot_instance):
        self.queue = Queue()
        self.active_tasks = {}
        self.max_tasks = CONFIG['max_parallel_tasks']
        self.bot = bot_instance
        self.processing_thread = None
        self._stop_flag = threading.Event()

    def start(self):
        """Start the processing thread"""
        self.processing_thread = threading.Thread(target=self._process_queue)
        self.processing_thread.daemon = True
        self.processing_thread.start()

    def stop(self):
        """Stop the processing thread"""
        self._stop_flag.set()
        if self.processing_thread:
            self.processing_thread.join()

    def add_task(self, task: TranscriptionTask):
        """Add a task to the queue"""
        self.queue.put(task)

    def _process_queue(self):
        """Main processing loop"""
        while not self._stop_flag.is_set():
            try:
                # Process tasks if slots are available
                while len(self.active_tasks) < self.max_tasks and not self.queue.empty():
                    task = self.queue.get()
                    thread = threading.Thread(
                        target=self._process_task,
                        args=(task,)
                    )
                    thread.daemon = True
                    thread.start()
                    self.active_tasks[id(thread)] = thread

                # Clean up completed tasks
                for task_id in list(self.active_tasks.keys()):
                    if not self.active_tasks[task_id].is_alive():
                        self.active_tasks[task_id].join()
                        del self.active_tasks[task_id]

                time.sleep(1)
            except Exception as e:
                logger.error(f"Error in processing loop: {e}")

    def _process_task(self, task: TranscriptionTask):
        """Process a single transcription task"""
        try:
            # Send initial status
            asyncio.run(self.bot.send_message(task.chat_id, "Starting transcription..."))

            if task.is_url:
                if is_youtube_url(task.file_path):
                    # Download YouTube video
                    file_path = download_youtube_video(task.file_path)
                elif is_google_drive_url(task.file_path):
                    # Download from Google Drive
                    file_id = get_drive_file_id(task.file_path)
                    if not file_id:
                        raise ValueError("Invalid Google Drive URL")
                    file_path = download_from_google_drive(file_id)
                else:
                    raise ValueError("Unsupported URL type")
            else:
                file_path = task.file_path

            # Perform transcription
            transcription = transcribe_audio(file_path)

            # Cleanup downloaded file if it was from URL
            if task.is_url:
                cleanup_temp_files(file_path)

            if transcription:
                # Save transcription to file
                temp_file = tempfile.NamedTemporaryFile(
                    delete=False,
                    suffix='.txt',
                    mode='w',
                    encoding='utf-8'
                )
                temp_file.write(transcription)
                temp_file.close()

                # Send the file
                asyncio.run(self.bot.send_file(
                    task.chat_id,
                    temp_file.name,
                    "Transcription completed!"
                ))

                # Cleanup
                os.unlink(temp_file.name)
            else:
                asyncio.run(self.bot.send_message(
                    task.chat_id,
                    "Transcription failed. Please try again."
                ))

        except Exception as e:
            logger.error(f"Error processing task: {e}")
            asyncio.run(self.bot.send_message(
                task.chat_id,
                f"Error during transcription: {str(e)}"
            ))

class TranscriptionBot:
    def __init__(self):
        self.whitelist: Set[int] = self.load_whitelist()
        self.queue = TranscriptionQueue(self)
        
        # Create temp directory if it doesn't exist
        os.makedirs(CONFIG['temp_dir'], exist_ok=True)

    def load_whitelist(self) -> Set[int]:
        """Load whitelisted user IDs from JSON file"""
        try:
            with open(CONFIG['whitelist_file'], 'r') as f:
                data = json.load(f)
                return set(data['allowed_users'])
        except FileNotFoundError:
            logger.warning(f"Whitelist file not found at {CONFIG['whitelist_file']}")
            return set([ALL_USERS])
        except json.JSONDecodeError:
            logger.error(f"Invalid JSON in whitelist file {CONFIG['whitelist_file']}")
            return set()

    def check_whitelist(self, user_id: int) -> bool:
        """Check if user is whitelisted"""
        return ALL_USERS in self.whitelist or user_id in self.whitelist

    async def send_message(self, chat_id: int, text: str):
        """Send a message to the user"""
        async with Application.builder().token(CONFIG['telegram_token']).build() as app:
            await app.bot.send_message(chat_id=chat_id, text=text)

    async def send_file(self, chat_id: int, file_path: str, caption: str):
        """Send a file to the user"""
        async with Application.builder().token(CONFIG['telegram_token']).build() as app:
            await app.bot.send_document(
                chat_id=chat_id,
                document=open(file_path, 'rb'),
                caption=caption
            )

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        if not self.check_whitelist(update.effective_user.id):
            await update.message.reply_text(
                "Sorry, you are not authorized to use this bot."
            )
            return

        await update.message.reply_text(
            "Welcome to the Transcription Bot!\n\n"
            "Use /transcribe (or /ts) command with either:\n"
            "- An audio/video file attachment\n"
            "- A YouTube URL\n"
            "- A public Google Drive file URL (should be an mp4 file)\n\n"
            "Supported formats: mp3, mp4, mpeg, mpga, m4a, wav, webm\n\n"
            "I will process your request and send you back the transcription."
        )

    async def handle_transcribe_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /transcribe or /ts command"""
        if not self.check_whitelist(update.effective_user.id):
            await update.message.reply_text(
                "Sorry, you are not authorized to use this bot."
            )
            return

        # Check if it's a URL
        if context.args:
            url = context.args[0]
            if is_youtube_url(url):
                await update.message.reply_text(
                    "Added YouTube video to transcription queue. "
                    "You will be notified when it's ready."
                )
                self.queue.add_task(TranscriptionTask(
                    chat_id=update.effective_chat.id,
                    file_path=url,
                    is_url=True
                ))
                return
            elif is_google_drive_url(url):
                await update.message.reply_text(
                    "Added Google Drive file to transcription queue. "
                    "You will be notified when it's ready."
                )
                self.queue.add_task(TranscriptionTask(
                    chat_id=update.effective_chat.id,
                    file_path=url,
                    is_url=True
                ))
                return
            else:
                await update.message.reply_text(
                    "Please provide either a YouTube URL, a Google Drive URL, "
                    "or attach an audio/video file."
                )
                return

        # Check if there's a file attachment
        if not update.message.document:
            await update.message.reply_text(
                "Please provide either a YouTube/Google Drive URL or attach an audio/video file."
            )
            return

        # Check file extension
        file_name = update.message.document.file_name.lower()
        file_ext = os.path.splitext(file_name)[1]
        if file_ext not in CONFIG['supported_formats']:
            await update.message.reply_text(
                f"Unsupported file format. Please use one of: "
                f"{', '.join(CONFIG['supported_formats'])}"
            )
            return

        logger.info(f"Received document with mime type: {update.message.document.mime_type}")
        # Check file size (size is in bytes, convert limit to bytes)
        MAX_FILE_SIZE = 20 * 1024 * 1024  # 20MB in bytes
        if update.message.document.file_size > MAX_FILE_SIZE:
            await update.message.reply_text(
                f"Sorry, the file is too big. Maximum allowed size is 20MB. "
                f"Your file is {round(update.message.document.file_size / (1024 * 1024), 1)}MB.\n\n"
                f"Please try:\n"
                f"1. Compressing the file first\n"
                f"2. Trimming the audio/video to a shorter duration\n"
                f"3. Reducing the quality\n"
                f"4. Using a YouTube or Google Drive link instead"
            )
            return

        # Download the file
        file = await context.bot.get_file(update.message.document.file_id)
        file_path = os.path.join(
            CONFIG['temp_dir'],
            f"{update.message.document.file_id}_{update.message.document.file_name}"
        )
        await file.download_to_drive(file_path)

        # Add to queue
        self.queue.add_task(TranscriptionTask(
            chat_id=update.effective_chat.id,
            file_path=file_path
        ))

        await update.message.reply_text(
            "File added to transcription queue. "
            "You will be notified when it's ready."
        )

    async def handle_document(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle any document/file sent to the bot"""
        # Redirect to the transcribe command handler
        await self.handle_transcribe_command(update, context)

def main():
    """Start the bot"""
    # Create bot instance
    bot = TranscriptionBot()
    
    # Start queue processing
    bot.queue.start()

    # Create application and add handlers
    application = Application.builder().token(CONFIG['telegram_token']).build()
    application.add_handler(CommandHandler('start', bot.start_command))
    application.add_handler(CommandHandler(['transcribe', 'ts'], bot.handle_transcribe_command))

    # Add handler for documents (files)
    application.add_handler(MessageHandler(
        filters.Document.ALL & ~filters.COMMAND,
        bot.handle_document
    ))

    # Start the bot
    try:
        application.run_polling()
    finally:
        # Cleanup
        bot.queue.stop()

if __name__ == '__main__':
    main()