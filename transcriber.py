import subprocess
import math
import os
import tempfile
from urllib.parse import urlparse, parse_qs
import requests
from openai import OpenAI
from dotenv import load_dotenv
import time

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

def is_google_drive_url(url):
    """Check if the given string is a Google Drive URL"""
    try:
        parsed = urlparse(url)
        return 'drive.google.com' in parsed.netloc
    except:
        return False

def get_drive_file_id(url):
    """Extract file ID from Google Drive URL"""
    try:
        if '/file/d/' in url:
            # Handle links like: https://drive.google.com/file/d/{fileid}/view
            file_id = url.split('/file/d/')[1].split('/')[0]
        elif 'id=' in url:
            # Handle links like: https://drive.google.com/open?id={fileid}
            parsed = urlparse(url)
            file_id = parse_qs(parsed.query)['id'][0]
        else:
            return None
        return file_id
    except:
        return None

def download_from_google_drive(file_id):
    """Download a video file from Google Drive public link using gdown"""
    print("Downloading from Google Drive...")
    
    try:
        import gdown
        
        # Create temporary file with .mp4 extension
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.mp4')
        output = temp_file.name
        temp_file.close()
        
        # Construct the URL
        url = f"https://drive.google.com/uc?id={file_id}"
        
        print(f"Downloading file to: {output}")
        
        # Download the file with progress bar
        gdown.download(url, output, quiet=False)
        
        # Verify the download
        if os.path.getsize(output) == 0:
            raise ValueError("Downloaded file is empty")
            
        return output
        
    except Exception as e:
        print(f"\nError downloading from Google Drive: {str(e)}")
        raise ValueError(
            "Could not download from Google Drive. "
            "Please ensure:\n"
            "1. The file is publicly accessible (anyone with link can view)\n"
            "2. The link is in format: drive.google.com/file/d/FILE_ID/view\n"
            "3. The file is a video file (mp4 or webm)"
        )

def download_youtube_video(url):
    """Download YouTube video using yt-dlp and return path to downloaded file"""
    print("Downloading YouTube video...")
    
    # Create temporary directory for download
    temp_dir = tempfile.mkdtemp()
    output_template = os.path.join(temp_dir, '%(title)s.%(ext)s')
    
    try:
        # Download video using yt-dlp with progress output
        options = [
            '--format', 'mp4',
            '--output', output_template,
            '--progress',
        ]
        if os.path.exists('cookies.txt')
            options.append('--cookies')
            options.append('cookies.txt')
        cmd = ['yt-dlp', *options, url]
        run_command_with_output(cmd, "Downloading with yt-dlp:")
        
        # Find the downloaded file
        files = os.listdir(temp_dir)
        if not files:
            raise Exception("No file downloaded")
        
        return os.path.join(temp_dir, files[0])
    except subprocess.CalledProcessError as e:
        print(f"Error downloading video: {e}")
        raise

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

def split_audio(file_path, chunk_size_mb=20):  # Reduced to 20MB to ensure we stay under limit
    """Split audio file into chunks smaller than the API limit"""
    print("\nSplitting audio into chunks...")
    
    MAX_CHUNK_SIZE = 25 * 1024 * 1024  # 25MB in bytes
    file_size = os.path.getsize(file_path)
    duration = get_audio_duration(file_path)
    
    if not duration:
        raise Exception("Could not determine audio duration")
    
    # Calculate how many chunks we need
    chunk_duration = duration * (chunk_size_mb * 1024 * 1024) / file_size
    num_chunks = math.ceil(duration / chunk_duration)
    
    chunks = []
    current_chunk = 0
    while current_chunk < num_chunks:
        start_time = current_chunk * chunk_duration
        # Use original file extension
        original_ext = os.path.splitext(file_path)[1]
        
        # Create temporary file
        try:
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=original_ext)
            temp_file_path = temp_file.name
            temp_file.close()  # Close the file handle immediately
            
            cmd = [
                'ffmpeg',
                '-i', file_path,
                '-ss', str(start_time),
                '-t', str(chunk_duration),
                '-c', 'copy',
                '-y',
                temp_file_path
            ]
            
            run_command_with_output(cmd, f"Extracting chunk {current_chunk+1}/{num_chunks}:")
            
            # Add a small delay to ensure ffmpeg has released the file
            time.sleep(0.5)
            
            # Verify the chunk size
            try:
                chunk_size = os.path.getsize(temp_file_path)
                if chunk_size > MAX_CHUNK_SIZE:
                    print(f"Chunk {current_chunk+1} too large ({chunk_size/1024/1024:.1f}MB), reducing duration...")
                    try:
                        os.unlink(temp_file_path)
                    except Exception as e:
                        print(f"Warning: Could not delete oversized chunk: {e}")
                    # Reduce chunk duration by 20% and try again
                    chunk_duration *= 0.8
                    num_chunks = math.ceil(duration / chunk_duration)
                    continue
                
                chunks.append(temp_file_path)
                current_chunk += 1
                
            except OSError as e:
                print(f"Error checking chunk size: {e}")
                # Try to clean up
                try:
                    os.unlink(temp_file_path)
                except:
                    pass
                raise
                
        except subprocess.CalledProcessError as e:
            print(f"Error splitting chunk {current_chunk+1}: {e}")
            # Try to clean up
            try:
                os.unlink(temp_file_path)
            except:
                pass
            raise
        except Exception as e:
            print(f"Unexpected error while splitting chunk {current_chunk+1}: {e}")
            # Try to clean up
            try:
                os.unlink(temp_file_path)
            except:
                pass
            raise
    
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
                max_retries = 3
                retry_count = 0
                
                while retry_count < max_retries:
                    try:
                        print(f"\nTranscribing chunk {i} of {len(chunks)}...")
                        with open(chunk_path, "rb") as audio_file:
                            response = client.audio.transcriptions.create(
                                model="whisper-1",
                                file=audio_file,
                                timeout=60  # 60 second timeout
                            )
                            full_transcription.append(response.text)
                            break  # Success, exit retry loop
                    except Exception as e:
                        retry_count += 1
                        print(f"Error on chunk {i} (attempt {retry_count}): {str(e)}")
                        if retry_count == max_retries:
                            print(f"Failed to transcribe chunk {i} after {max_retries} attempts")
                            raise
                        print(f"Retrying in 5 seconds...")
                        time.sleep(5)
                
                # Clean up temporary file
                try:
                    os.unlink(chunk_path)
                except Exception as e:
                    print(f"Warning: Could not delete temporary file {chunk_path}: {e}")
            
            return ' '.join(full_transcription)
        else:
            print("\nTranscribing audio...")
            with open(audio_file, "rb") as audio_file:
                response = client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    timeout=60  # 60 second timeout
                )
                return response.text
    except Exception as e:
        print(f"Error during transcription: {e}")
        print(f"Error type: {type(e)}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        return None

def cleanup_temp_files(file_path):
    """Clean up temporary files and directories"""
    try:
        if os.path.isfile(file_path):
            for _ in range(5):  # Try up to 5 times
                try:
                    os.unlink(file_path)
                    break
                except PermissionError:
                    time.sleep(1)  # Wait a second before retrying
                except Exception as e:
                    print(f"Warning: Could not clean up {file_path}: {e}")
                    break
        elif os.path.isdir(file_path):
            for root, dirs, files in os.walk(file_path, topdown=False):
                for name in files:
                    try:
                        os.unlink(os.path.join(root, name))
                    except Exception as e:
                        print(f"Warning: Could not clean up file {name}: {e}")
                for name in dirs:
                    try:
                        os.rmdir(os.path.join(root, name))
                    except Exception as e:
                        print(f"Warning: Could not clean up directory {name}: {e}")
            try:
                os.rmdir(file_path)
            except Exception as e:
                print(f"Warning: Could not clean up directory {file_path}: {e}")
    except Exception as e:
        print(f"Warning: Could not clean up {file_path}: {e}")
