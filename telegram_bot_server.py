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

# Import our services and transcription functions
from transcriber import get_media_processor
from youtube_service import YouTubeService
from google_drive_service import GoogleDriveService
from linkedin_service import LinkedInService

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
    'supported_formats': {'.mp3', '.mp4', '.mpeg', '.mpga', '.m4a', '.wav', '.webm', '.mkv', '.avi', '.mov'}
}

ALL_USERS = -1

@dataclass
class TranscriptionTask:
    chat_id: int
    file_path: str
    is_url: bool = False
    prompt: Optional[str] = None
    task_id: Optional[str] = None

class TranscriptionQueue:
    def __init__(self, bot_instance):
        self.queue = Queue()
        self.active_tasks = {}
        self.max_tasks = CONFIG['max_parallel_tasks']
        self.bot = bot_instance
        self.processing_thread = None
        self._stop_flag = threading.Event()
        self.media_processor = get_media_processor()

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
            status_msg = "🎬 Starting transcription..."
            if task.is_url:
                status_msg = "🔗 Processing URL..."
            asyncio.run(self.bot.send_message(task.chat_id, status_msg))

            if task.is_url:
                # Identify the source
                source_name = "Unknown"
                if YouTubeService.is_youtube_url(task.file_path):
                    source_name = "YouTube"
                elif GoogleDriveService.is_google_drive_url(task.file_path):
                    source_name = "Google Drive"
                elif LinkedInService.is_linkedin_url(task.file_path):
                    source_name = "LinkedIn"
                
                asyncio.run(self.bot.send_message(
                    task.chat_id, 
                    f"📥 Downloading from {source_name}..."
                ))
                
                if YouTubeService.is_youtube_url(task.file_path):
                    # Download YouTube video
                    file_path = YouTubeService.download_video(task.file_path)
                elif GoogleDriveService.is_google_drive_url(task.file_path):
                    # Download from Google Drive
                    file_id = GoogleDriveService.get_file_id(task.file_path)
                    if not file_id:
                        raise ValueError("Invalid Google Drive URL")
                    file_path = GoogleDriveService.download_file(f"https://drive.google.com/file/d/{file_id}/view")
                elif LinkedInService.is_linkedin_url(task.file_path):
                    # Download from LinkedIn
                    file_path = LinkedInService.download_video(task.file_path)
                else:
                    raise ValueError("Unsupported URL type")
                
                asyncio.run(self.bot.send_message(
                    task.chat_id, 
                    "✅ Download completed!"
                ))
            else:
                file_path = task.file_path

            # Get audio duration
            duration = self.media_processor.get_audio_duration(file_path)
            duration_str = ""
            if duration:
                minutes = int(duration // 60)
                seconds = int(duration % 60)
                duration_str = f" (Duration: {minutes}m {seconds}s)"
            
            asyncio.run(self.bot.send_message(
                task.chat_id, 
                f"🎤 Transcribing audio{duration_str}..."
            ))

            # Perform transcription
            response = self.media_processor.transcribe_audio(file_path, task.prompt)
            transcription = response.text if response else None

            # Cleanup downloaded file if it was from URL
            if task.is_url:
                self.media_processor.cleanup_temp_files(file_path)

            if transcription:
                asyncio.run(self.bot.send_message(
                    task.chat_id, 
                    "📝 Processing transcription..."
                ))
                
                # Save transcription to file
                temp_file = tempfile.NamedTemporaryFile(
                    delete=False,
                    suffix='.txt',
                    mode='w',
                    encoding='utf-8'
                )
                temp_file.write(transcription)
                temp_file.close()

                # Calculate some stats
                word_count = len(transcription.split())
                char_count = len(transcription)
                
                # Send the file with stats
                caption = f"✨ Transcription completed!\n\n"
                caption += f"📊 Stats:\n"
                caption += f"• Words: {word_count:,}\n"
                caption += f"• Characters: {char_count:,}\n"
                if duration:
                    caption += f"• Duration: {minutes}m {seconds}s"
                
                asyncio.run(self.bot.send_file(
                    task.chat_id,
                    temp_file.name,
                    caption
                ))

                # Cleanup
                os.unlink(temp_file.name)
            else:
                asyncio.run(self.bot.send_message(
                    task.chat_id,
                    "❌ Transcription failed. Please try again."
                ))

        except Exception as e:
            logger.error(f"Error processing task: {e}")
            error_msg = f"❌ Error during transcription:\n{str(e)}"
            
            # Add helpful tips for common errors
            if "file size" in str(e).lower():
                error_msg += "\n\n💡 Tip: Try using a URL instead of uploading the file directly."
            elif "unsupported" in str(e).lower():
                error_msg += "\n\n💡 Tip: Make sure your file is in a supported format (mp3, mp4, wav, etc.)"
            
            asyncio.run(self.bot.send_message(
                task.chat_id,
                error_msg
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
            "🎙️ Welcome to the Transcription Bot!\n\n"
            "📝 **How to use:**\n"
            "Send me `/transcribe` (or `/ts`) with:\n"
            "• 📎 An audio/video file (up to 20MB)\n"
            "• 🔗 A YouTube URL\n"
            "• 💼 A LinkedIn post URL\n"
            "• 📁 A Google Drive file URL\n\n"
            "💡 **Pro tip:** For larger files, use a link instead of direct upload!\n\n"
            "🎯 **Custom prompts:**\n"
            "Improve accuracy with domain-specific prompts:\n"
            "`/transcribe [URL] --prompt \"Technical discussion about AI\"`\n\n"
            "📋 **Supported formats:**\n"
            "mp3, mp4, mpeg, mpga, m4a, wav, webm, mkv, avi, mov\n\n"
            "✨ I'll transcribe your media and send you a text file with the results!"
        )

    async def handle_transcribe_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /transcribe or /ts command"""
        if not self.check_whitelist(update.effective_user.id):
            await update.message.reply_text(
                "Sorry, you are not authorized to use this bot."
            )
            return

        # Extract custom prompt if provided
        prompt = None
        args = context.args[:] if context.args else []
        
        if args and "--prompt" in args:
            prompt_index = args.index("--prompt")
            if prompt_index < len(args) - 1:
                # Get all text after --prompt flag
                prompt = " ".join(args[prompt_index + 1:])
                # Remove prompt args from the arguments list
                args = args[:prompt_index]
        
        # Check if it's a URL
        if args:
            url = args[0]
            source_type = ""
            
            if YouTubeService.is_youtube_url(url):
                source_type = "YouTube"
            elif GoogleDriveService.is_google_drive_url(url):
                source_type = "Google Drive"
            elif LinkedInService.is_linkedin_url(url):
                source_type = "LinkedIn"
                
            if source_type:
                prompt_info = f" with custom prompt" if prompt else ""
                await update.message.reply_text(
                    f"Added {source_type} video to transcription queue{prompt_info}. "
                    "You will be notified when it's ready."
                )
                self.queue.add_task(TranscriptionTask(
                    chat_id=update.effective_chat.id,
                    file_path=url,
                    is_url=True,
                    prompt=prompt
                ))
                return
            else:
                await update.message.reply_text(
                    "Please provide either a YouTube URL, a LinkedIn URL, a Google Drive URL, "
                    "or attach an audio/video file."
                )
                return

        # Check if there's a file attachment
        if not update.message.document:
            await update.message.reply_text(
                "Please provide either a YouTube/LinkedIn/Google Drive URL or attach an audio/video file.\n"
                "You can also add a custom prompt with: /transcribe [URL] --prompt \"Your custom prompt\""
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
                f"4. Using a YouTube, LinkedIn, or Google Drive link instead"
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
        prompt_info = " with custom prompt" if prompt else ""
        self.queue.add_task(TranscriptionTask(
            chat_id=update.effective_chat.id,
            file_path=file_path,
            prompt=prompt
        ))

        await update.message.reply_text(
            f"File added to transcription queue{prompt_info}. "
            "You will be notified when it's ready."
        )

    async def handle_document(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle any document/file sent to the bot"""
        # Redirect to the transcribe command handler
        await self.handle_transcribe_command(update, context)
    
    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /status command to show queue status"""
        if not self.check_whitelist(update.effective_user.id):
            await update.message.reply_text(
                "Sorry, you are not authorized to use this bot."
            )
            return
        
        queue_size = self.queue.queue.qsize()
        active_tasks = len(self.queue.active_tasks)
        
        status_msg = "📊 **Transcription Queue Status**\n\n"
        
        if queue_size == 0 and active_tasks == 0:
            status_msg += "✅ Queue is empty - ready for new tasks!"
        else:
            status_msg += f"🔄 Active tasks: {active_tasks}/{self.queue.max_tasks}\n"
            status_msg += f"⏳ Queued tasks: {queue_size}\n\n"
            
            if active_tasks > 0:
                status_msg += "💭 Currently processing transcriptions..."
        
        await update.message.reply_text(status_msg)
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command"""
        if not self.check_whitelist(update.effective_user.id):
            await update.message.reply_text(
                "Sorry, you are not authorized to use this bot."
            )
            return
        
        help_text = """🤖 **Transcription Bot Help**

**Available Commands:**
• `/start` - Welcome message and quick start guide
• `/help` - Show this help message
• `/transcribe` (or `/ts`) - Transcribe audio/video
• `/status` - Check queue status

**How to Transcribe:**
1️⃣ **Direct Upload:** Send a file with `/transcribe` or just send the file
   - Max size: 20MB (Telegram limit)
   - Formats: mp3, mp4, wav, m4a, webm, mkv, avi, mov

2️⃣ **From URL:** Send `/transcribe [URL]`
   - YouTube videos
   - LinkedIn posts
   - Google Drive files
   - No size limit! 🎉

**Pro Features:**
🎯 **Custom Prompts** for better accuracy:
`/transcribe [URL] --prompt "Medical terminology"`

📊 **Examples:**
• `/ts https://youtube.com/watch?v=...`
• `/ts https://drive.google.com/file/d/.../view`
• Send any audio/video file directly

💡 **Tips:**
• Use URLs for files larger than 20MB
• Custom prompts improve technical content accuracy
• Check `/status` to see queue progress

Need more help? Check the project documentation!"""
        
        await update.message.reply_text(help_text)

def main():
    """Start the bot"""
    # Create bot instance
    bot = TranscriptionBot()
    
    # Start queue processing
    bot.queue.start()

    # Create application and add handlers
    application = Application.builder().token(CONFIG['telegram_token']).build()
    application.add_handler(CommandHandler('start', bot.start_command))
    application.add_handler(CommandHandler('help', bot.help_command))
    application.add_handler(CommandHandler(['transcribe', 'ts'], bot.handle_transcribe_command))
    application.add_handler(CommandHandler('status', bot.status_command))

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