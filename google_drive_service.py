import os
import tempfile
from urllib.parse import urlparse, parse_qs


class GoogleDriveService:
    @staticmethod
    def is_google_drive_url(url):
        """Check if the given string is a Google Drive URL"""
        try:
            parsed = urlparse(url)
            return 'drive.google.com' in parsed.netloc
        except Exception:
            return False

    @staticmethod
    def get_file_id(url):
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
        except Exception:
            return None

    @staticmethod
    def download_file(url):
        """Download a video file from Google Drive public link"""
        print("Downloading from Google Drive...")
        
        try:
            import gdown
            
            # Get file ID from URL
            file_id = GoogleDriveService.get_file_id(url)
            if not file_id:
                raise ValueError("Invalid Google Drive URL")
            
            # Create temporary file with .mp4 extension
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.mp4')
            output = temp_file.name
            temp_file.close()
            
            # Construct the download URL
            download_url = f"https://drive.google.com/uc?id={file_id}"
            
            print(f"Downloading file to: {output}")
            
            # Download the file with progress bar
            gdown.download(download_url, output, quiet=False)
            
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
