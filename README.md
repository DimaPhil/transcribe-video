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

## Usage

### Web Interface

Start the web server:
```bash
python app.py
```

Then visit `http://localhost:3000` in your web browser.

The web interface allows you to:
- Upload local media files from your computer
- Load media from LinkedIn, YouTube, or Google Drive URLs
- Provide custom prompts to improve transcription quality
- Specify where to save transcription files
- Download completed transcriptions

### Telegram Bot

To use the Telegram bot:

1. Create a Telegram bot through BotFather and get the access token
2. Add your Telegram Bot token to `.env`
3. Optionally, create `whitelist.json` to restrict access:
   ```json
   {
       "allowed_users": [
           123456789, 987654321
       ]
   }
   ```
4. Start the bot:
   ```bash
   python telegram_bot_server.py
   ```

### Customizing Transcription with Prompts

You can improve transcription quality by creating a `system_prompt.txt` file in the root directory. This prompt will be used to guide the transcription model.

Examples of effective prompts:
- Industry-specific terminology: "This is a technical discussion about machine learning, mentioning terms like: TensorFlow, PyTorch, backpropagation, gradient descent."
- Speaker identification: "The conversation is between John (male with deep voice) and Sarah (female with higher-pitched voice)."
- Language guidance: "This is a bilingual conversation in English and Spanish."
- Format preferences: "Please include proper punctuation, capitalize proper nouns, and format numbers as digits."

### File Storage

By default, all media files are stored in the `temp_resources` directory, and transcriptions are saved to `temp_resources/transcriptions`. You can specify a custom location for transcription files in the web interface.