# Video Transcriber

A tool for transcribing video and audio files using OpenAI's GPT-4o Transcribe API.

## Features

- Transcribe video and audio files from various sources:
  - Local files uploaded through the web interface
  - LinkedIn videos
  - YouTube videos (with cookie authentication support)
  - Google Drive videos
- AI-powered summarization of transcriptions:
  - Support for multiple languages (English, Russian)
  - Custom prompt support for focused summaries
  - Iterative refinement based on feedback
  - Glossary support for domain-specific terms
- Supports multiple file formats: mp4, mp3, m4a, wav, webm, mkv, avi, mov, etc.
- Web interface with:
  - File upload from your computer (up to 5GB)
  - URL-based media loading
  - YouTube cookie authentication for restricted videos
  - Custom prompt support for better transcription quality
  - Configurable transcription save location
  - Download transcriptions directly from the UI
  - Collapsible transcription display
  - One-click summarization with language selection
  - Download summaries as text files
- Telegram bot with:
  - Large file support (up to 2GB with local API)
  - YouTube cookie management
  - Queue status tracking
  - Smart summarization with context tracking
  - Iterative summary refinement
- Automatic local saving of all transcriptions
- Security features:
  - Encrypted cookie storage
  - Automatic cookie deletion after 24 hours
  - Session-based cookie access

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

Then visit `http://localhost:8082` in your web browser.

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
4. (Optional) For large file support (up to 2GB), add Telegram API credentials:
   - Get API ID and Hash from https://my.telegram.org/apps
   - Add to `.env`: `TELEGRAM_API_ID=` and `TELEGRAM_API_HASH=`
5. The bot will start automatically with `docker-compose up -d`

**Bot Commands:**
- `/start` - Get welcome message and instructions
- `/help` - Show detailed help and examples
- `/transcribe` or `/ts` - Transcribe a file or URL
- `/summary` - Summarize transcriptions with AI
- `/status` - Check transcription queue status
- `/setcookies` - Upload YouTube cookies for restricted videos
- `/removecookies` - Delete stored cookies
- `/cancel` - Cancel current operation

**Features:**
- Direct file uploads:
  - Standard mode: up to 20MB
  - With local API server: up to 2GB
- URL support for YouTube, LinkedIn, and Google Drive (no size limit!)
- YouTube cookie authentication for restricted videos
- Custom prompts: `/transcribe [URL] --prompt "Technical AI discussion"`
- Real-time status updates with progress tracking
- Queue management for multiple concurrent transcriptions
- Automatic cookie deletion after 24 hours for security

### AI-Powered Summarization

The application includes advanced summarization capabilities powered by Claude AI, allowing you to quickly generate concise summaries of your transcriptions.

**Web Interface Features:**
- **Collapsible Transcription Display**: Long transcriptions show a preview with a "Read more" button
- **One-Click Summarization**: Click "Summarize" after transcription completes
- **Language Support**: Choose between English and Russian summaries
- **Custom Instructions**: Add specific guidance for the summary (e.g., "Focus on action items")
- **Download Options**: Save summaries as text files or copy to clipboard

**Telegram Bot Features:**
- **Smart Context Tracking**: Automatically summarizes your last transcription
- **Multiple Input Methods**:
  - `/summary` - Summarize the last transcription
  - `/summary Your text here` - Summarize provided text
  - `/summary` + attach .txt file - Summarize file contents
- **Natural Refinement**: After receiving a summary, just send your feedback as a regular message!
- **Intent Detection**: The bot intelligently detects when you want to refine a summary
- **Language Selection**: `/summary --lang ru` for Russian summaries
- **File + Text Output**: Receive summaries as both files and text (when size permits)

**Summarization Examples:**
```bash
# Summarize last transcription
/summary

# Summarize in Russian
/summary --lang ru

# Summarize with custom focus
/summary Focus on technical details and code examples

# After receiving a summary, refine naturally:
"Make it shorter and focus on action items"
"Add more details about the technical implementation"
"Please include the timeline discussed"
```

**Configuration:**
1. Add your Anthropic API key to `.env`: `ANTHROPIC_API_KEY=your_key_here`
2. System prompts are located in `summarization/` directory
3. Add domain-specific glossaries in `summarization/glossary/`

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

### YouTube Cookie Authentication

Some YouTube videos require authentication (age-restricted, private, or region-locked content). The transcriber supports cookie-based authentication:

**Web Interface:**
1. When entering a YouTube URL, a cookie upload section will appear
2. Export cookies using browser extensions like "Get cookies.txt" or "cookies.txt"
3. Upload the cookies.txt file
4. The cookies will be used for that download session only

**Telegram Bot:**
1. Use `/setcookies` command
2. Follow the instructions to export your YouTube cookies
3. Send the cookies.txt file to the bot
4. Cookies are stored securely and auto-deleted after 24 hours
5. Use `/removecookies` to manually delete them

**Security Notes:**
- Cookies are stored in encrypted form with random filenames
- Web interface uses session-based storage (expires on browser close)
- Telegram bot deletes cookies after 24 hours automatically
- Never share your cookies file with others
- Only use cookies from your own YouTube account

## Advanced Configuration

### Environment Variables

The following environment variables can be configured in your `.env` file:

**Required:**
- `OPENAI_API_KEY` - Your OpenAI API key for transcription
- `ANTHROPIC_API_KEY` - Your Anthropic API key for summarization (Claude)
- `TELEGRAM_BOT_TOKEN` - Your Telegram bot token (if using Telegram bot)

**Optional for Large File Support:**
- `TELEGRAM_API_ID` - Telegram API ID from https://my.telegram.org/apps
- `TELEGRAM_API_HASH` - Telegram API Hash from https://my.telegram.org/apps

**Advanced Path Configuration (rarely needed):**
- `TELEGRAM_API_DATA_DIR` - Path where telegram-bot-api stores files (default: `/var/lib/telegram-bot-api`)
- `TELEGRAM_API_MOUNT_PATH` - Mount path in telegram-bot container (default: `/telegram-bot-api-files`)

These path variables allow you to customize the file storage locations if needed, making the deployment more flexible for different environments.