# Video Transcriber

A tool for transcribing video and audio files using OpenAI's GPT-4o Transcribe API.

## Features

- Transcribe video and audio files from various sources:
  - Local files uploaded through the web interface
  - LinkedIn videos
  - YouTube videos
  - Google Drive videos
- Supports multiple file formats: mp4, mp3, m4a, wav, webm, mkv, avi, mov, etc.
- Web interface with:
  - File upload from your computer
  - URL-based media loading
  - Custom prompt support for better transcription quality
  - Configurable transcription save location
  - Download transcriptions directly from the UI
- Telegram bot for mobile use
- Automatic local saving of all transcriptions

## Installation

### Option 1: Standard Installation

1. Install required system dependencies:
   ```bash
   # For macOS
   brew install ffmpeg

   # For Linux
   sudo apt install -y ffmpeg
   ```

2. Install Python libraries:
   ```bash
   pip install -r requirements.txt
   ```

3. Set up environment variables:
   - Copy `.env.example` to `.env`
   - Add your OpenAI API key to `.env`
   - If using the Telegram bot, add your Telegram Bot token to `.env`

### Option 2: Docker Installation

1. Make sure Docker and Docker Compose are installed on your system

2. Set up environment variables:
   - Copy `.env.example` to `.env`
   - Add your OpenAI API key to `.env`
   - If using the Telegram bot, add your Telegram Bot token to `.env`

3. Configure Telegram bot access (optional):
   - Copy `whitelist.json.example` to `whitelist.json`
   - Add authorized Telegram user IDs:
     ```json
     {
         "allowed_users": [
             123456789,  // Replace with your Telegram user ID
             987654321   // Add more user IDs as needed
         ]
     }
     ```

4. Build and start the containers:
   ```bash
   docker-compose up -d
   ```

5. The application will be available at:
   - Web interface: http://localhost
   - Telegram bot: Running automatically (send /start to your bot)

## Usage

### Web Interface

If using standard installation, start the web server:
```bash
python app.py
```

Then visit `http://localhost:80` in your web browser.

If using Docker, visit `http://localhost` in your web browser.

The web interface allows you to:
- Upload local media files from your computer
- Load media from LinkedIn, YouTube, or Google Drive URLs
- Provide custom prompts to improve transcription quality
- Specify where to save transcription files
- Download completed transcriptions

### Telegram Bot

The Telegram bot runs automatically when using Docker. To set it up:

1. Create a Telegram bot through @BotFather and get the access token
2. Add your Telegram Bot token to `.env` file as `TELEGRAM_BOT_TOKEN=your_token_here`
3. Configure access by editing `whitelist.json` (see Docker installation step 3)
4. The bot will start automatically with `docker-compose up -d`

**Bot Commands:**
- `/start` - Get welcome message and instructions
- `/help` - Show detailed help and examples
- `/transcribe` or `/ts` - Transcribe a file or URL
- `/status` - Check transcription queue status

**Features:**
- Direct file uploads (up to 20MB via Telegram)
- URL support for YouTube, LinkedIn, and Google Drive (no size limit!)
- Custom prompts: `/transcribe [URL] --prompt "Technical AI discussion"`
- Real-time status updates with progress tracking
- Queue management for multiple concurrent transcriptions

### Customizing Transcription with Prompts

You can improve transcription quality by creating a `system_prompt.txt` file in the root directory. This prompt will be used to guide the transcription model.

Examples of effective prompts:
- Industry-specific terminology: "This is a technical discussion about machine learning, mentioning terms like: TensorFlow, PyTorch, backpropagation, gradient descent."
- Speaker identification: "The conversation is between John (male with deep voice) and Sarah (female with higher-pitched voice)."
- Language guidance: "This is a bilingual conversation in English and Spanish."
- Format preferences: "Please include proper punctuation, capitalize proper nouns, and format numbers as digits."

### File Storage

By default, all media files are stored in the `temp_resources` directory, and transcriptions are saved to `temp_resources/transcriptions`. You can specify a custom location for transcription files in the web interface.

When using Docker, these directories are persisted as volumes, so your files will remain even if you restart the container.

### Large File Support

The application supports large file uploads:

- **Web Interface**: Up to 5GB file uploads directly through the browser
- **Telegram Bot**: 
  - Direct uploads limited to 20MB (Telegram's limit)
  - For larger files, use URLs from YouTube, Google Drive, or LinkedIn
- **Docker Setup**: Includes nginx proxy configured for large uploads with proper timeouts

**Tips for large files:**
1. Use URL-based loading when possible (no size limits)
2. Ensure stable internet connection for uploads
3. The transcription will automatically split very large audio files into chunks
4. For files over 1GB, expect longer upload times

**Troubleshooting large uploads:**
- If you get a 413 error, restart Docker containers: `docker-compose down && docker-compose up -d`
- On Docker Desktop, check Docker's resource limits in preferences
- For files over 100MB, consider uploading to Google Drive/YouTube first, then use the URL