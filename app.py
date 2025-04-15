from flask import Flask, render_template, request, jsonify, send_from_directory
import os
import shutil
import datetime
from werkzeug.utils import secure_filename
from linkedin_service import LinkedInService
from google_drive_service import GoogleDriveService
from youtube_service import YouTubeService
from transcriber import get_media_processor
import tempfile
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = Flask(__name__)
TEMP_DIR = 'temp_resources'
TRANSCRIPTION_DIR = os.path.join(TEMP_DIR, 'transcriptions')
os.makedirs(TEMP_DIR, exist_ok=True)
os.makedirs(TRANSCRIPTION_DIR, exist_ok=True)

# File upload configuration
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100MB max upload size
ALLOWED_EXTENSIONS = {'mp3', 'mp4', 'mpeg', 'mpga', 'm4a', 'wav', 'webm', 'mkv', 'avi', 'mov'}

# Get singleton instance of MediaProcessorService
media_processor = get_media_processor()


def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def generate_timestamp():
    """Generate a timestamp string for filenames"""
    return datetime.datetime.now().strftime("%Y%m%d_%H%M%S")


def save_transcription(transcription, original_filename, output_dir=None):
    """Save transcription to file and return the path"""
    if not output_dir:
        output_dir = TRANSCRIPTION_DIR
    
    os.makedirs(output_dir, exist_ok=True)
    
    # Create a filename based on the original media file
    base_name = os.path.splitext(os.path.basename(original_filename))[0]
    timestamp = generate_timestamp()
    transcription_filename = f"{base_name}_{timestamp}.txt"
    safe_filename = secure_filename(transcription_filename)
    
    # Full path to save the transcription
    full_path = os.path.join(output_dir, safe_filename)
    
    # Save the transcription text
    with open(full_path, 'w', encoding='utf-8') as f:
        f.write(transcription)
    
    # Return the relative path from TEMP_DIR for serving
    return os.path.relpath(full_path, TEMP_DIR)


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/upload-file', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    
    file = request.files['file']
    
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400
    
    if not allowed_file(file.filename):
        return jsonify({'error': f'Unsupported file format. Allowed formats: {", ".join(ALLOWED_EXTENSIONS)}'}), 400
    
    try:
        # Create a temporary directory to store the uploaded file
        temp_dir = tempfile.mkdtemp(dir=TEMP_DIR)
        
        # Secure the filename and save the file
        filename = secure_filename(file.filename)
        file_path = os.path.join(temp_dir, filename)
        file.save(file_path)
        
        # Get the duration
        duration = media_processor.get_audio_duration(file_path)
        
        # Get the path relative to TEMP_DIR
        relative_path = os.path.relpath(file_path, TEMP_DIR)
        
        return jsonify({
            'success': True,
            'filename': relative_path,
            'video_path': file_path,
            'duration': round(duration, 2) if duration else None
        })
    except Exception as e:
        import traceback
        print(f"Error processing file upload: {str(e)}")
        print(traceback.format_exc())
        return jsonify({'error': str(e)}), 500


@app.route('/process-url', methods=['POST'])
def process_url():
    url = request.json.get('url')
    if not url:
        return jsonify({'error': 'No URL provided'}), 400
    
    try:
        temp_dir = tempfile.mkdtemp(dir=TEMP_DIR)
        
        if LinkedInService.is_linkedin_url(url):
            video_path = LinkedInService.download_video(url)
        elif GoogleDriveService.is_google_drive_url(url):
            video_path = GoogleDriveService.download_file(url)
        elif YouTubeService.is_youtube_url(url):
            video_path = YouTubeService.download_video(url)
        else:
            return jsonify({'error': 'Unsupported URL format'}), 400

        # Sanitize the filename - replace spaces and special characters
        original_filename = os.path.basename(video_path)
        safe_filename = ''.join(c for c in original_filename if c.isalnum() or c in '._-') 
        new_path = os.path.join(temp_dir, safe_filename)
        
        try:
            shutil.move(video_path, new_path)
        except Exception as e:
            print(f"Error moving file: {e}")
            try:
                shutil.copy2(video_path, new_path)
                os.unlink(video_path)
            except Exception as copy_error:
                print(f"Error during copy fallback: {copy_error}")
                raise
        
        original_dir = os.path.dirname(video_path)
        if original_dir != temp_dir and os.path.exists(original_dir):
            try:
                os.rmdir(original_dir)
            except Exception:
                pass

        duration = media_processor.get_audio_duration(new_path)
        
        # Get the path relative to TEMP_DIR
        relative_path = os.path.relpath(new_path, TEMP_DIR)
        
        return jsonify({
            'success': True,
            'filename': relative_path,
            'video_path': new_path,
            'duration': round(duration, 2) if duration else None
        })
    except Exception as e:
        import traceback
        print(f"Error processing URL: {str(e)}")
        print(traceback.format_exc())
        return jsonify({'error': str(e)}), 500


@app.route('/transcribe', methods=['POST'])
def transcribe_video():
    filename = request.json.get('file_path')  # This will now be just the filename
    prompt = request.json.get('prompt')  # Optional prompt parameter
    output_dir = request.json.get('output_dir')  # Optional output directory
    
    if not filename:
        return jsonify({'error': 'No file path provided'}), 400
    
    try:
        # Construct the full path using the filename
        local_path = os.path.join(TEMP_DIR, filename)
        
        print(f"Transcribing file: {local_path}")
        print(f"File exists: {os.path.exists(local_path)}")
        
        if not os.path.exists(local_path):
            print(f"Contents of {TEMP_DIR}:")
            for root, dirs, files in os.walk(TEMP_DIR):
                for name in files:
                    print(os.path.join(root, name))
            return jsonify({'error': f'File not found: {local_path}'}), 404

        response = media_processor.transcribe_audio(local_path, prompt)
        if not response:
            return jsonify({'error': 'Transcription failed'}), 500
            
        transcription = response.text
        
        # Save the transcription to a file
        transcription_path = save_transcription(transcription, local_path, output_dir)

        duration = media_processor.get_audio_duration(local_path)
        
        return jsonify({
            'transcription': transcription,
            'transcription_path': transcription_path,
            'duration': round(duration, 2) if duration else None
        })
    except Exception as e:
        import traceback
        print(f"Error during transcription: {str(e)}")
        print(traceback.format_exc())
        return jsonify({'error': str(e)}), 500


@app.route('/temp_resources/<path:filename>')
def serve_temp_file(filename):
    # Split the path into directory and filename
    directory = os.path.dirname(filename)
    basename = os.path.basename(filename)
    
    # Construct the full directory path
    full_dir = os.path.join(TEMP_DIR, directory) if directory else TEMP_DIR
    
    print(f"Serving file: {filename}")
    print(f"Full directory: {full_dir}")
    print(f"Basename: {basename}")
    
    return send_from_directory(full_dir, basename)


if __name__ == '__main__':
    app.run(port=80, host='0.0.0.0', debug=True)
