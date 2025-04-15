import os
import tempfile
import time
import math
import re
from pydub import AudioSegment
from openai import OpenAI
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class MediaProcessorService:
    def __init__(self):
        # Get API key from environment variables
        api_key = os.getenv('OPENAI_API_KEY')
        if not api_key:
            raise ValueError("OpenAI API key not found. Please set OPENAI_API_KEY in .env file.")
        
        self.client = OpenAI(api_key=api_key)
        self.supported_formats = ['.mp3', '.mp4', '.mpeg', '.mpga', '.m4a', '.wav', '.webm', '.mkv', '.avi', '.mov']
        
    def get_audio_duration(self, file_path):
        """Get the duration of an audio file using pydub"""
        try:
            # Identify file extension
            _, file_ext = os.path.splitext(file_path)
            file_ext = file_ext.lower()
            
            # Load audio file based on format
            if file_ext in ['.mp3', '.wav', '.m4a', '.mpga']:
                audio = AudioSegment.from_file(file_path, format=file_ext[1:])
            else:
                # For video files, extract audio and get duration
                temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.mp3')
                temp_file.close()
                
                audio = AudioSegment.from_file(file_path)
                audio.export(temp_file.name, format="mp3")
                
                audio = AudioSegment.from_mp3(temp_file.name)
                
                # Clean up temp file
                try:
                    os.unlink(temp_file.name)
                except Exception as e:
                    print(f"Warning: Could not delete temporary file: {e}")
            
            # Duration in seconds
            return len(audio) / 1000.0
        except Exception as e:
            print(f"Error getting duration: {e}")
            return None

    def extract_audio_from_file(self, file_path):
        """Extract audio from any media file and return the audio segment"""
        try:
            # Identify file extension
            _, file_ext = os.path.splitext(file_path)
            file_ext = file_ext.lower()
            
            # For audio files, load directly
            if file_ext in ['.mp3', '.wav', '.m4a', '.mpga']:
                return AudioSegment.from_file(file_path, format=file_ext[1:])
            # For video files, extract audio
            else:
                return AudioSegment.from_file(file_path)
        except Exception as e:
            print(f"Error extracting audio: {e}")
            raise ValueError(f"Failed to extract audio from {file_path}: {str(e)}")

    def split_audio(self, file_path, chunk_size_mb=20, overlap_seconds=5):
        """Split audio file into chunks smaller than the API limit using pydub with overlap"""
        print("\nSplitting audio into chunks...")
        
        MAX_CHUNK_SIZE = 25 * 1024 * 1024  # 25MB in bytes
        
        # Get file information
        file_size = os.path.getsize(file_path)
        duration = self.get_audio_duration(file_path)
        
        if not duration:
            raise Exception("Could not determine audio duration")
            
        # Calculate chunk parameters
        chunk_duration = duration * (chunk_size_mb * 1024 * 1024) / file_size
        chunk_duration_ms = int(chunk_duration * 1000)  # Convert to milliseconds for pydub
        overlap_ms = int(overlap_seconds * 1000)  # Overlap in milliseconds
        
        # Load the audio
        audio = self.extract_audio_from_file(file_path)
        total_audio_length = len(audio)
        
        print(f"Audio duration: {duration:.2f} seconds ({total_audio_length} ms)")
        print(f"Calculated chunk duration: {chunk_duration_ms/1000:.2f} seconds with {overlap_seconds}s overlap")
        
        # Calculate how many chunks we need - add 1 to ensure we have enough chunks
        effective_chunk_length = chunk_duration_ms - overlap_ms
        total_chunks = math.ceil(total_audio_length / effective_chunk_length)
        
        # Ensure we have at least one chunk
        total_chunks = max(1, total_chunks)
        
        print(f"Splitting into {total_chunks} chunks...")
        
        chunks = []
        chunk_info = []  # Store start and end times for debugging
        
        for i in range(total_chunks):
            # Calculate start and end times with overlap
            start_time = max(0, i * effective_chunk_length)
            
            # For the last chunk, always go to the end regardless of calculated duration
            if i == total_chunks - 1:
                end_time = total_audio_length
            else:
                end_time = min(total_audio_length, start_time + chunk_duration_ms)
            
            # Ensure we have the minimum overlap with the next chunk
            if i < total_chunks - 1 and end_time > total_audio_length - overlap_ms:
                end_time = total_audio_length
            
            # Create a temporary file for this chunk
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.mp3')
            temp_file.close()
            
            # Extract chunk
            audio_chunk = audio[start_time:end_time]
            audio_chunk.export(temp_file.name, format="mp3")
            
            # Check size
            chunk_size = os.path.getsize(temp_file.name)
            if chunk_size > MAX_CHUNK_SIZE:
                print(f"Chunk {i+1} too large ({chunk_size/1024/1024:.1f}MB), reducing size...")
                try:
                    os.unlink(temp_file.name)
                except Exception as e:
                    print(f"Warning: Could not delete oversized chunk: {e}")
                # Try again with a smaller chunk size
                return self.split_audio(file_path, chunk_size_mb * 0.8, overlap_seconds)
            
            chunks.append(temp_file.name)
            chunk_info.append((start_time, end_time))
            print(f"Chunk {i+1}/{total_chunks} created: {temp_file.name} (Start: {start_time/1000:.2f}s, End: {end_time/1000:.2f}s)")
        
        # Verify coverage of the entire audio
        if chunks and chunk_info:
            last_end_time = chunk_info[-1][1]
            if last_end_time < total_audio_length:
                print(f"Warning: Last chunk doesn't reach the end of audio. Missing {(total_audio_length - last_end_time)/1000:.2f} seconds")
                # Create a final chunk that overlaps with the previous one but goes to the end
                start_time = max(0, total_audio_length - chunk_duration_ms)
                end_time = total_audio_length
                
                temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.mp3')
                temp_file.close()
                
                audio_chunk = audio[start_time:end_time]
                audio_chunk.export(temp_file.name, format="mp3")
                
                chunks.append(temp_file.name)
                chunk_info.append((start_time, end_time))
                print(f"Added extra final chunk: (Start: {start_time/1000:.2f}s, End: {end_time/1000:.2f}s)")
        
        # Final verification
        if chunk_info:
            coverage = sum([(end - start) for start, end in chunk_info])
            expected_coverage = total_audio_length + (len(chunk_info) - 1) * overlap_ms  # Account for overlaps
            print(f"Total audio length: {total_audio_length/1000:.2f}s, Chunks cover: {coverage/1000:.2f}s with overlaps")
            
            # Check for gaps
            for i in range(len(chunk_info) - 1):
                current_end = chunk_info[i][1]
                next_start = chunk_info[i+1][0]
                if next_start > current_end:
                    print(f"Warning: Gap between chunks {i+1} and {i+2}: {(next_start - current_end)/1000:.2f}s")
        
        return chunks, chunk_info

    def find_best_overlap(self, prev_text, curr_text, min_overlap_words=5, max_overlap_words=30):
        """Find the best overlap between two text segments using suffix-prefix matching"""
        if not prev_text or not curr_text:
            return None, 0
            
        # Split texts into words
        prev_words = prev_text.split()
        curr_words = curr_text.split()
        
        # Limit the search to a reasonable range
        max_overlap = min(len(prev_words), len(curr_words), max_overlap_words)
        
        best_overlap = None
        best_overlap_len = 0
        
        # Try different overlap sizes, from largest to smallest
        for overlap_len in range(max_overlap, min_overlap_words - 1, -1):
            # Get the last N words of previous text
            prev_suffix = ' '.join(prev_words[-overlap_len:])
            # Get the first N words of current text
            curr_prefix = ' '.join(curr_words[:overlap_len])
            
            # Check if the suffix of prev matches the prefix of curr
            if prev_suffix == curr_prefix:
                # Found a match
                best_overlap = prev_suffix
                best_overlap_len = overlap_len
                break
                
        return best_overlap, best_overlap_len

    def clean_transcription_segment(self, text):
        """Clean and normalize a transcription segment"""
        if not text:
            return ""
        
        # Normalize whitespace
        text = re.sub(r'\s+', ' ', text.strip())
        return text

    def combine_transcription_segments(self, segments):
        """Combine transcription segments into a single text, handling overlaps intelligently"""
        if not segments:
            return ""
        
        if len(segments) == 1:
            return segments[0]
        
        print(f"Combining {len(segments)} segments")
        
        # Strategy: Find overlaps between adjacent segments and merge them
        combined_text = segments[0]
        
        for i in range(1, len(segments)):
            current_segment = segments[i]
            
            # Skip empty segments
            if not current_segment.strip():
                print(f"Warning: Skipping empty segment {i}")
                continue
                
            # Minimum overlap length to consider (words)
            min_overlap_len = 4
            
            # Maximum overlap to search for (characters)
            max_search_chars = 500
            
            # Get the last part of the combined text and the first part of the current segment
            last_part = combined_text[-max_search_chars:] if len(combined_text) > max_search_chars else combined_text
            first_part = current_segment[:max_search_chars] if len(current_segment) > max_search_chars else current_segment
            
            # Find the longest common substring
            overlap = self.find_longest_common_string(last_part, first_part, min_overlap_len)
            
            if overlap:
                # Find where the overlap begins in the combined text
                overlap_start = combined_text.rfind(overlap)
                if overlap_start != -1:
                    # Add only the non-overlapping part of the current segment
                    overlap_end_in_current = current_segment.find(overlap) + len(overlap)
                    combined_text = combined_text[:overlap_start] + current_segment[current_segment.find(overlap):]
                    print(f"Found overlap of {len(overlap)} characters between segments {i-1} and {i}")
                else:
                    # If overlap detection failed, just append with a space
                    combined_text += " " + current_segment
                    print(f"No valid overlap position found between segments {i-1} and {i}")
            else:
                # If no significant overlap is found, just append with a space
                combined_text += " " + current_segment
                print(f"No significant overlap found between segments {i-1} and {i}")
        
        return combined_text
        
    def find_longest_common_string(self, str1, str2, min_words=4):
        """Find the longest common substring that has at least min_words words"""
        # Convert strings to lowercase for better matching
        str1_lower = str1.lower()
        str2_lower = str2.lower()
        
        # Split into words
        words1 = str1_lower.split()
        words2 = str2_lower.split()
        
        best_match = ""
        
        # Start with larger sequences and work down
        for seq_len in range(min(len(words1), len(words2)), min_words-1, -1):
            # Check all possible sequences of this length
            for i in range(len(words1) - seq_len + 1):
                sequence = " ".join(words1[i:i+seq_len])
                
                # Only consider sequences with sufficient words
                if len(sequence.split()) >= min_words:
                    # Look for this sequence in str2
                    if sequence in str2_lower:
                        # Get the original case version from str1
                        original_case = " ".join(str1.split()[i:i+seq_len])
                        return original_case
        
        return best_match

    def transcribe_audio(self, audio_file, prompt=None):
        """Transcribe audio from a file, with support for large files via chunking"""
        max_api_size_mb = 25
        file_size_mb = os.path.getsize(audio_file) / (1024 * 1024)
        
        print(f"Transcribing audio file: {audio_file} (Size: {file_size_mb:.2f}MB)")
        
        # Load system prompt for consistency instructions if no prompt provided
        if prompt is None:
            system_prompt_path = "system_prompt.txt"
            if os.path.exists(system_prompt_path):
                with open(system_prompt_path, "r") as f:
                    prompt = f.read().strip()
                print(f"Using system prompt from {system_prompt_path}")
        
        # Load the audio data
        try:
            audio = AudioSegment.from_file(audio_file)
            print(f"Audio loaded: {len(audio)/1000:.2f} seconds")
        except Exception as e:
            error_msg = f"Error loading audio file: {e}"
            print(error_msg)
            raise ValueError(error_msg)
        
        # Initialize lists to store transcription segments and failed chunks
        transcription_segments = []
        failed_chunks = []
        
        # Check if we need to split the audio (over size limit or very long)
        if file_size_mb > max_api_size_mb or len(audio) > 30 * 60 * 1000:  # > 30 minutes
            print(f"Audio exceeds size limit for single API call. Splitting into chunks.")
            
            # Add 5-second overlap between chunks to handle sentences that span chunk boundaries
            chunk_duration_ms = 10 * 60 * 1000  # 10 minutes in milliseconds
            overlap_ms = 5 * 1000  # 5 seconds overlap
            
            total_audio_length = len(audio)
            effective_chunk_length = chunk_duration_ms - overlap_ms
            total_chunks = math.ceil(total_audio_length / effective_chunk_length)
            
            print(f"Splitting into {total_chunks} chunks with {overlap_ms/1000}s overlap")
            
            # Process each chunk
            for i in range(total_chunks):
                start_time = i * effective_chunk_length
                end_time = min(start_time + chunk_duration_ms, total_audio_length)
                
                # Special handling for the last chunk to ensure we reach the end
                if i == total_chunks - 1:
                    end_time = total_audio_length
                
                # Ensure we have the minimum overlap with the next chunk
                if i < total_chunks - 1 and end_time > total_audio_length - overlap_ms:
                    end_time = total_audio_length
                
                chunk_duration = (end_time - start_time) / 1000  # in seconds
                print(f"Processing chunk {i+1}/{total_chunks}: {start_time/1000:.1f}s to {end_time/1000:.1f}s (duration: {chunk_duration:.1f}s)")
                
                # Extract the chunk
                audio_chunk = audio[start_time:end_time]
                
                # Save the chunk temporarily
                chunk_file = f"temp_chunk_{i}.mp3"
                audio_chunk.export(chunk_file, format="mp3")
                
                # Try to transcribe the chunk (with retries)
                success = False
                max_retries = 3
                attempts = 0
                chunk_text = ""
                
                while not success and attempts < max_retries:
                    attempts += 1
                    try:
                        # Add context about which part of the audio this is
                        chunk_prompt = prompt
                        if prompt:
                            position_info = f"This is part {i+1} of {total_chunks} of the full audio."
                            chunk_prompt = f"{prompt}\n\n{position_info}"
                        
                        print(f"Attempt {attempts}/{max_retries} for chunk {i+1}")
                        chunk_response = self.client.audio.transcriptions.create(
                            model="whisper-1",
                            file=open(chunk_file, "rb"),
                            prompt=chunk_prompt
                        )
                        chunk_text = chunk_response.text
                        
                        # Validate the transcription - check if it's suspiciously short
                        expected_min_chars = chunk_duration * 5  # Rough estimate: 5 chars per second minimum
                        if len(chunk_text) < expected_min_chars and chunk_duration > 10:  # Only warn for chunks > 10s
                            print(f"Warning: Chunk {i+1} transcription suspiciously short: {len(chunk_text)} chars for {chunk_duration:.1f}s audio")
                        else:
                            print(f"Chunk {i+1} transcription successful: {len(chunk_text)} chars")
                        
                        # Store the transcription
                        transcription_segments.append(chunk_text)
                        success = True
                        
                    except Exception as e:
                        print(f"Error transcribing chunk {i+1} (attempt {attempts}): {e}")
                        if attempts >= max_retries:
                            print(f"Failed to transcribe chunk {i+1} after {max_retries} attempts")
                            failed_chunks.append(i+1)
                    
                    finally:
                        # Clean up the temporary file
                        if os.path.exists(chunk_file):
                            os.remove(chunk_file)
                
                # If chunk failed after all retries, add an empty segment or placeholder
                if not success:
                    transcription_segments.append(f"[Transcription failed for audio from {start_time/1000:.1f}s to {end_time/1000:.1f}s]")
            
            # Check if we have any successful transcriptions
            if not any(seg for seg in transcription_segments if not seg.startswith("[Transcription failed")):
                error_msg = f"All {total_chunks} chunks failed to transcribe. Audio may be corrupted or unsupported."
                print(error_msg)
                raise ValueError(error_msg)
            
            # Combine the transcription segments
            combined_text = self.combine_transcription_segments(transcription_segments)
            
            # Log the final transcription length and failed chunks
            print(f"Final transcription complete: {len(combined_text)} characters")
            if failed_chunks:
                print(f"Warning: {len(failed_chunks)} chunks failed to transcribe: {failed_chunks}")
            
            # Create a response-like object
            class TranscriptionResponse:
                def __init__(self, text):
                    self.text = text
            
            return TranscriptionResponse(combined_text)
        
        else:
            # For smaller files, just use the API directly
            print("Audio within size limits. Transcribing in one call.")
            try:
                response = self.client.audio.transcriptions.create(
                    model="whisper-1",
                    file=open(audio_file, "rb"),
                    prompt=prompt
                )
                print(f"Transcription complete: {len(response.text)} characters")
                return response
            except Exception as e:
                error_msg = f"Error during transcription: {e}"
                print(error_msg)
                raise ValueError(error_msg)

    def cleanup_temp_files(self, file_path):
        """Clean up temporary files and directories"""
        try:
            if os.path.isfile(file_path):
                for _ in range(5):  # Try up to 5 times
                    try:
                        os.unlink(file_path)
                        break
                    except PermissionError:
                        time.sleep(1)
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

# Singleton instance of MediaProcessorService
_media_processor_instance = None

def get_media_processor():
    """Get the singleton instance of MediaProcessorService"""
    global _media_processor_instance
    if _media_processor_instance is None:
        _media_processor_instance = MediaProcessorService()
    return _media_processor_instance

# For backward compatibility with telegram_bot_server.py
def transcribe_audio(audio_file, prompt=None):
    processor = get_media_processor()
    return processor.transcribe_audio(audio_file, prompt)

def cleanup_temp_files(file_path):
    processor = get_media_processor()
    return processor.cleanup_temp_files(file_path)

def is_youtube_url(url):
    from youtube_service import YouTubeService
    return YouTubeService.is_youtube_url(url)

def download_youtube_video(url):
    from youtube_service import YouTubeService
    return YouTubeService.download_video(url)

def is_google_drive_url(url):
    from google_drive_service import GoogleDriveService
    return GoogleDriveService.is_google_drive_url(url)

def get_drive_file_id(url):
    from google_drive_service import GoogleDriveService
    return GoogleDriveService.get_file_id(url)

def download_from_google_drive(file_id):
    from google_drive_service import GoogleDriveService
    return GoogleDriveService.download_file(f"https://drive.google.com/file/d/{file_id}/view")