# Video Transcriber

This tool implements a simple video transcriber using OpenAI Whisperer API.

## Installation

- Install `ffmpeg`, e.g. `brew install ffmpeg`;
- Install `yt-dlp`, e.g. `brew install yt-dlp`;
- Install Python libraries: `pip install -r requirements.txt`

## Execution

You can either use `trancriber.py` as a "library", or start a Telegram bot that can handle all videos and return transcription in a human-readable way.

- Set up a Telegram bot and save its access token
- Copy `.env.example` to `.env` and fill in all keys there (OpenAI + Telegram Bot access token).
- Optionally, create `whitelist.json` to configure the list of user ids who will be allowed to use this bot. You can get your Telegram ID in this [bot](https://t.me/username_to_id_bot).
	- The format is as follows:
	```json
	{
	    "allowed_users": [
	        11111, 22222
	    ]
	}
	```

To start the Telegram Bot server, use:
```bash
python telegram_bot_server.py
```