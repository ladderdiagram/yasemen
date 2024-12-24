from flask import Flask, request, send_file, render_template
import os
import subprocess
import logging
from werkzeug.utils import secure_filename
import json
import io
import time
import traceback
from functools import partial

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

# FFmpeg işlemleri için timeout değeri (saniye)
FFMPEG_TIMEOUT = 300

# subprocess.run için wrapper fonksiyon
def run_command_with_timeout(cmd, timeout=FFMPEG_TIMEOUT):
    try:
        return subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            timeout=timeout
        )
    except subprocess.TimeoutExpired:
        logger.error(f"Command timed out after {timeout} seconds: {' '.join(cmd)}")
        raise
    except subprocess.CalledProcessError as e:
        logger.error(f"Command failed: {e.stderr.decode() if e.stderr else str(e)}")
        raise

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
    temp_black_video = None
    
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
        temp_black_video = os.path.join(UPLOAD_FOLDER, f"black_{timestamp}.mp4")
        output_path = os.path.join(UPLOAD_FOLDER, f"merged_{timestamp}.mp4")
        
        logger.info(f"Saving uploaded video to {user_video_path}")
        user_video.save(user_video_path)

        # Video.mp4'ün çözünürlüğünü al
        cmd = [
            'ffprobe',
            '-v', 'error',
            '-select_streams', 'v:0',
            '-show_entries', 'stream=width,height',
            '-of', 'json',
            STATIC_VIDEO
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        video_info = json.loads(result.stdout)
        target_width = video_info['streams'][0]['width']
        target_height = video_info['streams'][0]['height']
        
        # Kullanıcının videosunu ölçeklendir
        scale_cmd = [
            'ffmpeg',
            '-i', user_video_path,
            '-vf', f'scale={target_width}:{target_height}:force_original_aspect_ratio=decrease,pad={target_width}:{target_height}:(ow-iw)/2:(oh-ih)/2',
            '-c:v', 'libx264',
            '-preset', 'ultrafast',
            '-crf', '23',
            temp_scaled_video
        ]
        subprocess.run(scale_cmd, check=True)
        
        # 3 saniyelik siyah video oluştur
        black_cmd = [
            'ffmpeg',
            '-f', 'lavfi',
            '-i', f'color=c=black:s={target_width}x{target_height}:d=3',
            '-c:v', 'libx264',
            '-preset', 'ultrafast',
            '-crf', '23',
            temp_black_video
        ]
        subprocess.run(black_cmd, check=True)
        
        # Birleştirme için çıktı dosyası
        output_path = os.path.join(UPLOAD_FOLDER, f"merged_{timestamp}.mp4")
        
        # Videoları birleştir ve müziği ekle
        command = [
            "ffmpeg",
            "-i", STATIC_VIDEO,
            "-i", temp_scaled_video,
            "-i", temp_black_video,
            "-i", STATIC_AUDIO,
            "-filter_complex", "[0:v][1:v][2:v]concat=n=3:v=1:a=0[outv]",
            "-map", "[outv]",
            "-map", "3:a",
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-crf", "23",
            "-c:a", "aac",
            "-b:a", "192k",
            output_path
        ]
        
        subprocess.run(command, check=True)
        
        # Dosyayı gönder
        try:
            with open(output_path, 'rb') as f:
                data = f.read()
            
            response = send_file(
                io.BytesIO(data),
                mimetype='video/mp4',
                as_attachment=True,
                download_name='yasemen.mp4'
            )
            
            # Temizlik
            for file_path in [user_video_path, output_path, temp_scaled_video, temp_black_video]:
                if file_path and os.path.exists(file_path):
                    os.remove(file_path)
                    
            return response
            
        except Exception as e:
            raise Exception(f"Dosya gönderme hatası: {str(e)}")
        
    except Exception as e:
        # Hata durumunda temizlik
        for file_path in [user_video_path, output_path, temp_scaled_video, temp_black_video]:
            if file_path and os.path.exists(file_path):
                os.remove(file_path)
        return str(e), 500

@app.route("/")
def main():
    return render_template('main.html')

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port, debug=True)
