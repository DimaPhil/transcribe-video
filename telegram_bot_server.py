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
    'telegram_api_url': os.getenv('TELEGRAM_BOT_API_URL'),
    'telegram_api_data_dir': os.getenv('TELEGRAM_API_DATA_DIR', '/var/lib/telegram-bot-api'),
    'telegram_api_mount_path': os.getenv('TELEGRAM_API_MOUNT_PATH', '/telegram-bot-api-files'),
    'whitelist_file': 'whitelist.json',
    'temp_dir': 'temp_files',
    'cookies_dir': 'temp_files/.cookies',
    'supported_formats': {'.mp3', '.mp4', '.mpeg', '.mpga', '.m4a', '.wav', '.webm', '.mkv', '.avi', '.mov'}
}

# Create cookies directory
os.makedirs(CONFIG['cookies_dir'], exist_ok=True)

ALL_USERS = -1

@dataclass
class TranscriptionTask:
    chat_id: int
    file_path: str
    is_url: bool = False
    prompt: Optional[str] = None
    task_id: Optional[str] = None
    cookies_path: Optional[str] = None

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
                    file_path = YouTubeService.download_video(task.file_path, task.cookies_path)
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
        self.user_cookies: Dict[int, str] = {}  # Store user cookies paths
        
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
        logger.info(f"Whitelist check: User {user_id}, Whitelist: {self.whitelist}")
        return ALL_USERS in self.whitelist or user_id in self.whitelist

    def _get_application_builder(self):
        """Get application builder with local API if configured"""
        builder = Application.builder().token(CONFIG['telegram_token'])
        if CONFIG['telegram_api_url']:
            builder = builder.base_url(CONFIG['telegram_api_url'])
            builder = builder.local_mode(True)
            # Increase timeouts for large file downloads
            builder = builder.connect_timeout(30.0)
            builder = builder.read_timeout(300.0)  # 5 minutes for large files
            builder = builder.write_timeout(300.0)
        return builder

    async def send_message(self, chat_id: int, text: str):
        """Send a message to the user"""
        async with self._get_application_builder().build() as app:
            await app.bot.send_message(chat_id=chat_id, text=text)

    async def send_file(self, chat_id: int, file_path: str, caption: str):
        """Send a file to the user"""
        async with self._get_application_builder().build() as app:
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

        local_api_msg = ""
        if CONFIG['telegram_api_url']:
            local_api_msg = "\n\n🚀 **Enhanced Mode Active:** Large file support up to 2GB!"
        
        await update.message.reply_text(
            "🎙️ Welcome to the Transcription Bot!\n\n"
            "📝 **How to use:**\n"
            "Send me `/transcribe` (or `/ts`) with:\n"
            f"• 📎 An audio/video file (up to {2048 if CONFIG['telegram_api_url'] else 20}MB)\n"
            "• 🔗 A YouTube URL\n"
            "• 💼 A LinkedIn post URL\n"
            "• 📁 A Google Drive file URL\n\n"
            "💡 **Pro tip:** For larger files, use a link instead of direct upload!\n\n"
            "🎯 **Custom prompts:**\n"
            "Improve accuracy with domain-specific prompts:\n"
            "`/transcribe [URL] --prompt \"Technical discussion about AI\"`\n\n"
            "🍪 **YouTube Authentication:**\n"
            "Use `/setcookies` to upload YouTube cookies for restricted videos\n\n"
            "📋 **Supported formats:**\n"
            "mp3, mp4, mpeg, mpga, m4a, wav, webm, mkv, avi, mov\n\n"
            f"✨ I'll transcribe your media and send you a text file with the results!{local_api_msg}"
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
                # Check if user has uploaded cookies for YouTube
                cookies_path = None
                if source_type == "YouTube" and update.effective_user.id in self.user_cookies:
                    cookies_path = self.user_cookies[update.effective_user.id]
                
                self.queue.add_task(TranscriptionTask(
                    chat_id=update.effective_chat.id,
                    file_path=url,
                    is_url=True,
                    prompt=prompt,
                    cookies_path=cookies_path
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
        # Check if we're using local API
        if CONFIG['telegram_api_url']:
            # With local API, we can handle much larger files
            MAX_FILE_SIZE = 2 * 1024 * 1024 * 1024  # 2GB
        else:
            # Standard Bot API limit
            MAX_FILE_SIZE = 20 * 1024 * 1024  # 20MB
            
        if update.message.document.file_size > MAX_FILE_SIZE:
            size_mb = round(update.message.document.file_size / (1024 * 1024), 1)
            max_mb = round(MAX_FILE_SIZE / (1024 * 1024), 1)
            await update.message.reply_text(
                f"Sorry, the file is too big. Maximum allowed size is {max_mb}MB. "
                f"Your file is {size_mb}MB.\n\n"
                f"Please try:\n"
                f"1. Using a YouTube, LinkedIn, or Google Drive link instead\n"
                f"2. Compressing the file first\n"
                f"3. Trimming the audio/video to a shorter duration"
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
        logger.warning("*** DOCUMENT HANDLER CALLED ***")
        logger.warning(f"Received document from user {update.effective_user.id}: {update.message.document.file_name}")
        
        # First check if user is whitelisted
        if not self.check_whitelist(update.effective_user.id):
            logger.warning(f"Unauthorized user {update.effective_user.id} tried to send document")
            await update.message.reply_text(
                "Sorry, you are not authorized to use this bot."
            )
            return
        
        # Check if we're expecting cookies
        if context.user_data.get('expecting_cookies'):
            logger.info("Redirecting to cookies handler")
            await self.handle_cookies_file(update, context)
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

        logger.info(f"Processing document with mime type: {update.message.document.mime_type}")
        
        # Check if we're using local API
        if CONFIG['telegram_api_url']:
            # With local API, we can handle much larger files
            MAX_FILE_SIZE = 2 * 1024 * 1024 * 1024  # 2GB
        else:
            # Standard Bot API limit
            MAX_FILE_SIZE = 20 * 1024 * 1024  # 20MB
            
        if update.message.document.file_size > MAX_FILE_SIZE:
            size_mb = round(update.message.document.file_size / (1024 * 1024), 1)
            max_mb = round(MAX_FILE_SIZE / (1024 * 1024), 1)
            await update.message.reply_text(
                f"Sorry, the file is too big. Maximum allowed size is {max_mb}MB. "
                f"Your file is {size_mb}MB.\n\n"
                f"Please try:\n"
                f"1. Using a YouTube, LinkedIn, or Google Drive link instead\n"
                f"2. Compressing the file first\n"
                f"3. Trimming the audio/video to a shorter duration"
            )
            return

        # Download the file
        try:
            await update.message.reply_text("📥 Downloading file...")
            file = await context.bot.get_file(update.message.document.file_id)
            file_path = os.path.join(
                CONFIG['temp_dir'],
                f"{update.message.document.file_id}_{update.message.document.file_name}"
            )
            
            # For local API, download differently
            if CONFIG['telegram_api_url']:
                # In local mode, files are stored on the filesystem
                # We need to copy them from the telegram-bot-api container
                try:
                    import httpx
                    
                    # Get file info to get the actual path
                    base_url = CONFIG['telegram_api_url'].rstrip('/')
                    file_info_url = f"{base_url}{CONFIG['telegram_token']}/getFile"
                    file_data = {"file_id": update.message.document.file_id}
                    
                    async with httpx.AsyncClient(timeout=300.0) as client:
                        resp = await client.post(file_info_url, json=file_data)
                        resp.raise_for_status()
                        file_info = resp.json()
                        
                        if not file_info.get('ok'):
                            raise Exception(f"Failed to get file info: {file_info}")
                        
                        # Get the actual file path
                        actual_file_path = file_info['result']['file_path']
                        logger.info(f"File path from API: {actual_file_path}")
                        
                        # Map the container path to the volume mount
                        if actual_file_path.startswith(CONFIG['telegram_api_data_dir']):
                            volume_path = actual_file_path.replace(
                                CONFIG['telegram_api_data_dir'], 
                                CONFIG['telegram_api_mount_path']
                            )
                            
                            # Check if file exists in the volume
                            if os.path.exists(volume_path):
                                import shutil
                                shutil.copy2(volume_path, file_path)
                                logger.info(f"File copied from volume: {volume_path} to {file_path}")
                            else:
                                logger.error(f"File not found in volume: {volume_path}")
                                raise Exception(f"File not found in shared volume: {volume_path}")
                        else:
                            raise Exception(f"Unexpected file path format: {actual_file_path}")
                            
                except Exception as e:
                    logger.error(f"Failed to download file: {e}")
                    raise
            else:
                await file.download_to_drive(file_path)
                
        except Exception as e:
            logger.error(f"Error downloading document: {e}")
            await update.message.reply_text(
                f"❌ Error downloading file: {str(e)}\n\n"
                "Please try using a YouTube/Google Drive URL instead."
            )
            return

        # Add to queue
        self.queue.add_task(TranscriptionTask(
            chat_id=update.effective_chat.id,
            file_path=file_path,
            prompt=None
        ))

        await update.message.reply_text(
            "File added to transcription queue. "
            "You will be notified when it's ready."
        )
    
    async def handle_media(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle media files (video, audio, voice) sent to the bot"""
        logger.warning("*** MEDIA HANDLER CALLED ***")
        logger.warning(f"Received media from user {update.effective_user.id}")
        
        # First check if user is whitelisted
        if not self.check_whitelist(update.effective_user.id):
            logger.warning(f"Unauthorized user {update.effective_user.id} tried to send media")
            await update.message.reply_text(
                "Sorry, you are not authorized to use this bot."
            )
            return
        
        # Check if there's a caption with transcribe command
        prompt = None
        if update.message.caption:
            caption = update.message.caption.strip()
            logger.info(f"Media caption: {caption}")
            
            # Check if caption starts with /transcribe or /ts
            if caption.startswith(('/transcribe', '/ts')):
                # Extract prompt if provided
                parts = caption.split(None, 1)
                if len(parts) > 1 and "--prompt" in parts[1]:
                    prompt_parts = parts[1].split("--prompt", 1)
                    if len(prompt_parts) > 1:
                        prompt = prompt_parts[1].strip()
        
        # Determine the type of media and get file info
        file_obj = None
        file_name = None
        
        if update.message.video:
            file_obj = update.message.video
            file_name = f"video_{update.message.video.file_id}.mp4"
            logger.info(f"Processing video: {file_name}")
        elif update.message.audio:
            file_obj = update.message.audio
            file_name = file_obj.file_name or f"audio_{update.message.audio.file_id}.mp3"
            logger.info(f"Processing audio: {file_name}")
        elif update.message.voice:
            file_obj = update.message.voice
            file_name = f"voice_{update.message.voice.file_id}.ogg"
            logger.info(f"Processing voice: {file_name}")
        
        if not file_obj:
            await update.message.reply_text(
                "Unable to process this media type. Please send an audio or video file."
            )
            return
        
        # Check if we're using local API
        if CONFIG['telegram_api_url']:
            # With local API, we can handle much larger files
            MAX_FILE_SIZE = 2 * 1024 * 1024 * 1024  # 2GB
        else:
            # Standard Bot API limit
            MAX_FILE_SIZE = 20 * 1024 * 1024  # 20MB
            
        if file_obj.file_size and file_obj.file_size > MAX_FILE_SIZE:
            size_mb = round(file_obj.file_size / (1024 * 1024), 1)
            max_mb = round(MAX_FILE_SIZE / (1024 * 1024), 1)
            await update.message.reply_text(
                f"Sorry, the file is too big. Maximum allowed size is {max_mb}MB. "
                f"Your file is {size_mb}MB.\n\n"
                f"Please try:\n"
                f"1. Using a YouTube, LinkedIn, or Google Drive link instead\n"
                f"2. Compressing the file first\n"
                f"3. Trimming the audio/video to a shorter duration"
            )
            return

        # Download the file
        try:
            await update.message.reply_text("📥 Downloading file...")
            logger.info(f"Getting file info for: {file_obj.file_id}")
            file = await context.bot.get_file(file_obj.file_id)
            logger.info(f"File path from API: {file.file_path}")
            
            file_path = os.path.join(
                CONFIG['temp_dir'],
                file_name
            )
            logger.info(f"Downloading to: {file_path}")
            
            # For local API, download differently
            if CONFIG['telegram_api_url']:
                # In local mode, files are stored on the filesystem
                # We need to copy them from the telegram-bot-api container
                try:
                    import httpx
                    
                    # Get file info to get the actual path
                    base_url = CONFIG['telegram_api_url'].rstrip('/')
                    file_info_url = f"{base_url}{CONFIG['telegram_token']}/getFile"
                    file_data = {"file_id": file_obj.file_id}
                    
                    async with httpx.AsyncClient(timeout=300.0) as client:
                        resp = await client.post(file_info_url, json=file_data)
                        resp.raise_for_status()
                        file_info = resp.json()
                        
                        if not file_info.get('ok'):
                            raise Exception(f"Failed to get file info: {file_info}")
                        
                        # Get the actual file path
                        actual_file_path = file_info['result']['file_path']
                        logger.info(f"File path from API: {actual_file_path}")
                        
                        # Map the container path to the volume mount
                        if actual_file_path.startswith(CONFIG['telegram_api_data_dir']):
                            volume_path = actual_file_path.replace(
                                CONFIG['telegram_api_data_dir'], 
                                CONFIG['telegram_api_mount_path']
                            )
                            
                            # Check if file exists in the volume
                            if os.path.exists(volume_path):
                                import shutil
                                shutil.copy2(volume_path, file_path)
                                logger.info(f"File copied from volume: {volume_path} to {file_path}")
                            else:
                                logger.error(f"File not found in volume: {volume_path}")
                                raise Exception(f"File not found in shared volume: {volume_path}")
                        else:
                            raise Exception(f"Unexpected file path format: {actual_file_path}")
                            
                except Exception as e:
                    logger.error(f"Failed to download file: {e}")
                    raise
            else:
                # Standard API download
                await file.download_to_drive(file_path)
            
            logger.info(f"Download completed: {file_path}")
        except Exception as e:
            logger.error(f"Error downloading file: {e}")
            logger.error(f"File ID: {file_obj.file_id}")
            logger.error(f"File size: {file_obj.file_size}")
            await update.message.reply_text(
                f"❌ Error downloading file: {str(e)}\n\n"
                "Please try uploading a smaller file or using a YouTube/Google Drive URL."
            )
            return

        # Add to queue
        self.queue.add_task(TranscriptionTask(
            chat_id=update.effective_chat.id,
            file_path=file_path,
            prompt=prompt
        ))

        prompt_info = " with custom prompt" if prompt else ""
        await update.message.reply_text(
            f"Media file added to transcription queue{prompt_info}. "
            "You will be notified when it's ready."
        )
    
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
    
    async def setcookies_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /setcookies command for YouTube authentication"""
        if not self.check_whitelist(update.effective_user.id):
            await update.message.reply_text(
                "Sorry, you are not authorized to use this bot."
            )
            return
        
        await update.message.reply_text(
            "🍪 **YouTube Cookie Setup**\n\n"
            "To transcribe age-restricted or private YouTube videos, I need your cookies.\n\n"
            "**How to export cookies:**\n"
            "1️⃣ Install browser extension: 'Get cookies.txt' or 'cookies.txt'\n"
            "2️⃣ Go to YouTube and sign in\n"
            "3️⃣ Click the extension and export cookies for youtube.com\n"
            "4️⃣ Send me the cookies.txt file\n\n"
            "⚠️ **Security Warning:**\n"
            "• Cookies give access to your YouTube account\n"
            "• They'll be stored securely and deleted after 24h\n"
            "• Only send cookies from your own account\n"
            "• Never share your cookies file with others\n\n"
            "Send me the cookies.txt file now, or /cancel to abort."
        )
        
        # Set a flag to expect cookies file
        context.user_data['expecting_cookies'] = True
    
    async def handle_cookies_file(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle cookies file upload"""
        if not context.user_data.get('expecting_cookies'):
            return
        
        if not update.message.document:
            await update.message.reply_text(
                "Please send a cookies.txt file or /cancel to abort."
            )
            return
        
        # Check file extension
        if not update.message.document.file_name.endswith('.txt'):
            await update.message.reply_text(
                "Please send a valid cookies.txt file."
            )
            return
        
        try:
            # Download the cookies file
            file = await context.bot.get_file(update.message.document.file_id)
            
            # Generate unique filename for this user
            user_id = update.effective_user.id
            cookies_filename = f"cookies_{user_id}_{int(time.time())}.txt"
            cookies_path = os.path.join(CONFIG['cookies_dir'], cookies_filename)
            
            await file.download_to_drive(cookies_path)
            
            # Store the path
            self.user_cookies[user_id] = cookies_path
            
            # Clear the flag
            context.user_data['expecting_cookies'] = False
            
            await update.message.reply_text(
                "✅ **Cookies saved successfully!**\n\n"
                "Your YouTube cookies have been securely stored.\n"
                "You can now transcribe restricted YouTube videos.\n\n"
                "The cookies will be automatically deleted after 24 hours.\n"
                "Use /removecookies to delete them manually."
            )
            
            # Schedule deletion after 24 hours
            # In production, you'd want to use a proper scheduler
            threading.Timer(24 * 3600, lambda: self._delete_user_cookies(user_id)).start()
            
        except Exception as e:
            logger.error(f"Error saving cookies: {e}")
            await update.message.reply_text(
                "❌ Failed to save cookies. Please try again."
            )
        finally:
            context.user_data['expecting_cookies'] = False
    
    def _delete_user_cookies(self, user_id: int):
        """Delete user's cookies file"""
        if user_id in self.user_cookies:
            cookies_path = self.user_cookies[user_id]
            if os.path.exists(cookies_path):
                try:
                    os.unlink(cookies_path)
                except Exception as e:
                    logger.error(f"Error deleting cookies: {e}")
            del self.user_cookies[user_id]
    
    async def removecookies_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /removecookies command"""
        if not self.check_whitelist(update.effective_user.id):
            await update.message.reply_text(
                "Sorry, you are not authorized to use this bot."
            )
            return
        
        user_id = update.effective_user.id
        if user_id in self.user_cookies:
            self._delete_user_cookies(user_id)
            await update.message.reply_text(
                "✅ Your YouTube cookies have been deleted."
            )
        else:
            await update.message.reply_text(
                "ℹ️ You don't have any stored cookies."
            )
    
    async def cancel_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /cancel command"""
        if context.user_data.get('expecting_cookies'):
            context.user_data['expecting_cookies'] = False
            await update.message.reply_text("Cancelled cookie upload.")
        else:
            await update.message.reply_text("Nothing to cancel.")
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command"""
        if not self.check_whitelist(update.effective_user.id):
            await update.message.reply_text(
                "Sorry, you are not authorized to use this bot."
            )
            return
        
        max_size = "2GB" if CONFIG['telegram_api_url'] else "20MB"
        help_text = f"""🤖 **Transcription Bot Help**

**Available Commands:**
• `/start` - Welcome message and quick start guide
• `/help` - Show this help message
• `/transcribe` (or `/ts`) - Transcribe audio/video
• `/status` - Check queue status
• `/setcookies` - Upload YouTube cookies for restricted videos
• `/removecookies` - Delete your stored cookies
• `/cancel` - Cancel current operation

**How to Transcribe:**
1️⃣ **Direct Upload:** Send a file with `/transcribe` or just send the file
   - Max size: {max_size}
   - Formats: mp3, mp4, wav, m4a, webm, mkv, avi, mov

2️⃣ **From URL:** Send `/transcribe [URL]`
   - YouTube videos (with cookie support!)
   - LinkedIn posts
   - Google Drive files
   - No size limit! 🎉

**YouTube Authentication:**
🍪 Use `/setcookies` to upload cookies for:
   - Age-restricted videos
   - Private/unlisted videos
   - Region-locked content

**Pro Features:**
🎯 **Custom Prompts** for better accuracy:
`/transcribe [URL] --prompt "Medical terminology"`

📊 **Examples:**
• `/ts https://youtube.com/watch?v=...`
• `/ts https://drive.google.com/file/d/.../view`
• Send any audio/video file directly

💡 **Tips:**
• Use URLs for files larger than {max_size}
• Custom prompts improve technical content accuracy
• Check `/status` to see queue progress
• Cookies are auto-deleted after 24h for security

Need more help? Check the project documentation!"""
        
        await update.message.reply_text(help_text)

def main():
    """Start the bot"""
    logger.info("Starting Telegram bot...")
    
    # Log configuration
    logger.info(f"Telegram API URL: {CONFIG['telegram_api_url']}")
    logger.info(f"Local mode enabled: {bool(CONFIG['telegram_api_url'])}")
    
    
    # Create bot instance
    bot = TranscriptionBot()
    logger.info(f"Whitelist loaded with {len(bot.whitelist)} users")
    
    # Start queue processing
    bot.queue.start()
    logger.info("Queue processing started")

    # Create application and add handlers
    builder = Application.builder().token(CONFIG['telegram_token'])
    if CONFIG['telegram_api_url']:
        builder = builder.base_url(CONFIG['telegram_api_url'])
        builder = builder.local_mode(True)
        # Increase timeouts for large file downloads
        builder = builder.connect_timeout(30.0)
        builder = builder.read_timeout(300.0)  # 5 minutes for large files
        builder = builder.write_timeout(300.0)
    application = builder.build()
    
    # Add error handler for debugging
    async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Log errors caused by updates."""
        logger.error(f"Exception while handling an update: {context.error}")
        if update:
            logger.error(f"Update: {update}")
    
    application.add_error_handler(error_handler)
    
    application.add_handler(CommandHandler('start', bot.start_command))
    application.add_handler(CommandHandler('help', bot.help_command))
    application.add_handler(CommandHandler(['transcribe', 'ts'], bot.handle_transcribe_command))
    application.add_handler(CommandHandler('status', bot.status_command))
    application.add_handler(CommandHandler('setcookies', bot.setcookies_command))
    application.add_handler(CommandHandler('removecookies', bot.removecookies_command))
    application.add_handler(CommandHandler('cancel', bot.cancel_command))

    # Add handler for documents (files)
    # Note: Order matters - more specific handlers should come first
    print("*** REGISTERING DOCUMENT HANDLER ***")
    application.add_handler(MessageHandler(
        filters.Document.ALL,
        bot.handle_document
    ))
    print("*** DOCUMENT HANDLER REGISTERED ***")
    
    # Add handler for videos sent as media (not documents)
    application.add_handler(MessageHandler(
        filters.VIDEO | filters.AUDIO | filters.VOICE,
        bot.handle_media
    ))
    
    # Remove catch-all for now to let proper handlers work

    # Start the bot
    try:
        logger.info("Starting bot polling...")
        application.run_polling(allowed_updates=Update.ALL_TYPES)
    except Exception as e:
        logger.error(f"Bot error: {e}")
        raise
    finally:
        # Cleanup
        logger.info("Stopping bot...")
        bot.queue.stop()

if __name__ == '__main__':
    main()