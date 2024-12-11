import subprocess
import math
import os
import tempfile
from urllib.parse import urlparse
from openai import OpenAI
from dotenv import load_dotenv


load_dotenv()

# Initialize the OpenAI client
client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))

def run_command_with_output(cmd, desc=None):
    """Run a command and stream its output in real-time"""
    if desc:
        print(f"\n{desc}")
    
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True,
        bufsize=1
    )
    
    output = []
    for line in iter(process.stdout.readline, ''):
        print(line, end='')
        output.append(line)
    
    process.stdout.close()
    return_code = process.wait()
    
    if return_code != 0:
        raise subprocess.CalledProcessError(return_code, cmd)
    
    return ''.join(output)

def is_youtube_url(url):
    """Check if the given string is a YouTube URL"""
    try:
        parsed = urlparse(url)
        return ('youtube.com' in parsed.netloc or 'youtu.be' in parsed.netloc)
    except:
        return False

def download_youtube_video(url):
    """Download YouTube video using yt-dlp and return path to downloaded file"""
    print("Downloading YouTube video...")
    
    # Create temporary directory for download
    temp_dir = tempfile.mkdtemp()
    output_template = os.path.join(temp_dir, '%(title)s.%(ext)s')
    
    try:
        # Download video using yt-dlp with progress output
        cmd = [
            'yt-dlp',
            '--format', 'mp4',
            '--output', output_template,
            '--progress',
            url
        ]
        run_command_with_output(cmd, "Downloading with yt-dlp:")
        
        # Find the downloaded file
        files = os.listdir(temp_dir)
        if not files:
            raise Exception("No file downloaded")
        
        return os.path.join(temp_dir, files[0])
    except subprocess.CalledProcessError as e:
        print(f"Error downloading video: {e}")
        raise

def convert_to_mp3(input_file):
    """Convert video file to MP3 format"""
    # Create temporary file for MP3
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.mp3')
    output_path = temp_file.name
    temp_file.close()
    
    try:
        cmd = [
            'ffmpeg',
            '-i', input_file,
            '-vn',  # Disable video
            '-acodec', 'libmp3lame',
            '-y',  # Overwrite output file
            output_path
        ]
        run_command_with_output(cmd, "Converting to MP3:")
        return output_path
    except subprocess.CalledProcessError as e:
        if os.path.exists(output_path):
            os.unlink(output_path)
        raise Exception(f"Error converting to MP3: {e}")

def get_audio_duration(file_path):
    """Get the duration of an audio file using ffprobe"""
    cmd = [
        'ffprobe', 
        '-v', 'quiet',
        '-show_entries', 'format=duration',
        '-of', 'default=noprint_wrappers=1:nokey=1',
        file_path
    ]
    try:
        output = subprocess.check_output(cmd)
        return float(output)
    except:
        return None

def split_audio(file_path, chunk_size_mb=24):
    """Split audio file into chunks smaller than the API limit"""
    print("\nSplitting audio into chunks...")
    
    file_size = os.path.getsize(file_path)
    duration = get_audio_duration(file_path)
    
    if not duration:
        raise Exception("Could not determine audio duration")
    
    # Calculate how many chunks we need
    chunk_duration = duration * (chunk_size_mb * 1024 * 1024) / file_size
    num_chunks = math.ceil(duration / chunk_duration)
    
    chunks = []
    for i in range(num_chunks):
        start_time = i * chunk_duration
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.mp3')
        
        # Use ffmpeg to extract chunk
        cmd = [
            'ffmpeg',
            '-i', file_path,
            '-ss', str(start_time),
            '-t', str(chunk_duration),
            '-acodec', 'libmp3lame',
            '-y',
            temp_file.name
        ]
        
        try:
            run_command_with_output(cmd, f"Extracting chunk {i+1}/{num_chunks}:")
            chunks.append(temp_file.name)
        except subprocess.CalledProcessError as e:
            print(f"Error splitting chunk {i+1}: {e}")
            if os.path.exists(temp_file.name):
                os.unlink(temp_file.name)
            continue
    
    return chunks

def transcribe_audio(audio_file):
    """Transcribe an audio file to text, handling files larger than the API limit"""
    try:
        # Check file size
        file_size = os.path.getsize(audio_file)
        max_size = 25 * 1024 * 1024  # 25MB in bytes
        
        if file_size > max_size:
            print(f"\nFile size ({file_size / 1024 / 1024:.2f}MB) exceeds API limit. Splitting into chunks...")
            chunks = split_audio(audio_file)
            
            if not chunks:
                raise Exception("Failed to split audio file into chunks")
                
            full_transcription = []
            
            for i, chunk_path in enumerate(chunks, 1):
                print(f"\nTranscribing chunk {i} of {len(chunks)}...")
                with open(chunk_path, "rb") as audio_file:
                    response = client.audio.transcriptions.create(
                        model="whisper-1",
                        file=audio_file
                    )
                    full_transcription.append(response.text)
                
                # Clean up temporary file
                os.unlink(chunk_path)
            
            return ' '.join(full_transcription)
        else:
            print("\nTranscribing audio...")
            with open(audio_file, "rb") as audio_file:
                response = client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file
                )
                return response.text
    except Exception as e:
        print(f"Error during transcription: {e}")
        return None

def cleanup_temp_files(file_path):
    """Clean up temporary files and directories"""
    try:
        if os.path.isfile(file_path):
            os.unlink(file_path)
        elif os.path.isdir(file_path):
            for root, dirs, files in os.walk(file_path, topdown=False):
                for name in files:
                    os.unlink(os.path.join(root, name))
                for name in dirs:
                    os.rmdir(os.path.join(root, name))
            os.rmdir(file_path)
    except Exception as e:
        print(f"Warning: Could not clean up {file_path}: {e}")