from flask import Flask, request, send_file, render_template
import os
import subprocess
import logging
from werkzeug.utils import secure_filename
import json
import io
import time
import traceback

app = Flask(__name__)

# Logging ayarları
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Halihazırdaki dosyalar
STATIC_VIDEO = "static/video.mp4"
STATIC_AUDIO = "static/audio.mp3"
UPLOAD_FOLDER = "uploads"

# Uploads klasörünü oluştur ve izinlerini ayarla
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    # Klasöre yazma izni ver
    os.chmod(UPLOAD_FOLDER, 0o777)

def get_media_duration(file_path):
    try:
        cmd = [
            'ffmpeg',
            '-i', file_path,
            '-f', 'null',
            '-'
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, stderr=subprocess.PIPE)
        # FFmpeg duration bilgisini stderr'den al
        for line in result.stderr.split('\n'):
            if "Duration" in line:
                time_str = line.split("Duration: ")[1].split(",")[0]
                h, m, s = time_str.split(':')
                return float(h) * 3600 + float(m) * 60 + float(s)
        return 0
    except Exception as e:
        logger.error(f"Duration check error: {str(e)}")
        return 0

@app.route("/merge", methods=["POST"])
def merge_video():
    user_video_path = None
    output_path = None
    temp_scaled_video = None
    
    try:
        logger.info("Starting merge process")
        
        if "userVideo" not in request.files:
            return "Dosya yüklenmedi", 400
            
        user_video = request.files["userVideo"]
        if user_video.filename == '':
            return "Dosya seçilmedi", 400
            
        # Dosya yollarını oluştur
        timestamp = int(time.time())
        user_video_path = os.path.join(UPLOAD_FOLDER, f"input_{timestamp}.mp4")
        temp_scaled_video = os.path.join(UPLOAD_FOLDER, f"scaled_{timestamp}.mp4")
        output_path = os.path.join(UPLOAD_FOLDER, f"output_{timestamp}.mp4")
        
        logger.info(f"Saving uploaded video to {user_video_path}")
        user_video.save(user_video_path)
        
        # FFmpeg version kontrolü
        try:
            ffmpeg_version = subprocess.check_output(['ffmpeg', '-version'])
            logger.info(f"FFmpeg version: {ffmpeg_version.decode('utf-8').split()[2]}")
        except Exception as e:
            logger.error(f"FFmpeg check failed: {str(e)}")
            return "FFmpeg not found", 500

        # Video işleme
        try:
            logger.info("Processing video...")
            
            # Ölçeklendirme komutu
            scale_cmd = [
                'ffmpeg', '-y',
                '-i', user_video_path,
                '-c:v', 'libx264',
                '-preset', 'medium',
                '-crf', '23',
                temp_scaled_video
            ]
            
            logger.info(f"Running scale command: {' '.join(scale_cmd)}")
            subprocess.run(scale_cmd, check=True, capture_output=True)
            
            # Birleştirme komutu
            merge_cmd = [
                'ffmpeg', '-y',
                '-i', STATIC_VIDEO,
                '-i', temp_scaled_video,
                '-i', STATIC_AUDIO,
                '-filter_complex', '[0:v][1:v]concat=n=2:v=1:a=0[outv]',
                '-map', '[outv]',
                '-map', '2:a',
                '-c:v', 'libx264',
                '-preset', 'medium',
                '-crf', '23',
                output_path
            ]
            
            logger.info(f"Running merge command: {' '.join(merge_cmd)}")
            subprocess.run(merge_cmd, check=True, capture_output=True)
            
        except subprocess.CalledProcessError as e:
            logger.error(f"FFmpeg error: {e.stderr.decode() if e.stderr else str(e)}")
            return f"Video processing error: {str(e)}", 500
            
        # Dosyayı gönder
        try:
            logger.info(f"Sending file: {output_path}")
            return send_file(
                output_path,
                mimetype='video/mp4',
                as_attachment=True,
                download_name='yasemen.mp4'
            )
            
        except Exception as e:
            logger.error(f"File send error: {str(e)}")
            return f"File send error: {str(e)}", 500
            
    except Exception as e:
        logger.error(f"General error: {str(e)}\n{traceback.format_exc()}")
        return f"An error occurred: {str(e)}", 500
        
    finally:
        # Temizlik
        try:
            for path in [user_video_path, temp_scaled_video, output_path]:
                if path and os.path.exists(path):
                    os.remove(path)
        except Exception as e:
            logger.error(f"Cleanup error: {str(e)}")

@app.route("/")
def main():
    return render_template('main.html')

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
