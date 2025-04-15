import os
import tempfile
from urllib.parse import urlparse, parse_qs
import yt_dlp


class YouTubeService:
    @staticmethod
    def is_youtube_url(url):
        """Check if the given string is a YouTube URL"""
        try:
            parsed = urlparse(url)
            return ('youtube.com' in parsed.netloc or 
                    'youtu.be' in parsed.netloc or 
                    'yt.be' in parsed.netloc)
        except Exception:
            return False

    @staticmethod
    def get_video_id(url):
        """Extract video ID from YouTube URL"""
        try:
            parsed = urlparse(url)
            if parsed.netloc in ['youtube.com', 'www.youtube.com']:
                if parsed.path == '/watch':
                    # https://www.youtube.com/watch?v=VIDEO_ID
                    return parse_qs(parsed.query)['v'][0]
                elif '/embed/' in parsed.path:
                    # https://www.youtube.com/embed/VIDEO_ID
                    return parsed.path.split('/embed/')[1]
                elif '/v/' in parsed.path:
                    # https://www.youtube.com/v/VIDEO_ID
                    return parsed.path.split('/v/')[1]
            elif parsed.netloc in ['youtu.be', 'yt.be']:
                # https://youtu.be/VIDEO_ID
                return parsed.path[1:]
            
            return None
        except Exception:
            return None

    @staticmethod
    def download_video(url):
        """Download YouTube video using yt-dlp and return path to downloaded file"""
        print("Downloading YouTube video...")
        
        temp_dir = tempfile.mkdtemp(dir='temp_resources')
        output_template = os.path.join(temp_dir, '%(title)s.%(ext)s')
        
        try:
            # Download video using yt-dlp
            ydl_opts = {
                'format': 'bestaudio/best',
                'outtmpl': output_template,
                'quiet': False,
                'no_warnings': False,
                'progress': True,
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
            
            # Find the downloaded file
            for root, _, files in os.walk(temp_dir):
                for file in files:
                    return os.path.join(root, file)
            
            raise Exception("No file downloaded")
        except Exception as e:
            print(f"Error downloading video: {e}")
            raise ValueError(f"Failed to download YouTube video: {str(e)}") 