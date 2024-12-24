from flask import Flask, request, send_file, render_template
import os
import subprocess
from werkzeug.utils import secure_filename
import json
import time
import io

app = Flask(__name__)

# Halihazırdaki dosyalar
STATIC_VIDEO = "static/video.mp4"
STATIC_AUDIO = "static/audio.mp3"
UPLOAD_FOLDER = "uploads"  # Yüklenen dosyalar için klasör

# Uploads klasörünü oluştur
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

def get_media_duration(file_path):
    """Medya dosyasının süresini saniye cinsinden döndürür"""
    cmd = [
        'ffprobe', 
        '-v', 'quiet',
        '-print_format', 'json',
        '-show_format',
        file_path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    data = json.loads(result.stdout)
    return float(data['format']['duration'])

try:
    ffmpeg_version = subprocess.check_output(['ffmpeg', '-version'])
    print("FFmpeg version:", ffmpeg_version.decode('utf-8').split('\n')[0])
except Exception as e:
    print("FFmpeg error:", str(e))

@app.route("/merge", methods=["POST"])
def merge_video():
    user_video_path = None
    output_path = None
    temp_scaled_video = None
    temp_black_video = None
    
    try:
        if "userVideo" not in request.files:
            return "Dosya yüklenmedi", 400
            
        user_video = request.files["userVideo"]
        if user_video.filename == '':
            return "Dosya seçilmedi", 400
            
        # Kullanıcının videosunu kaydet
        user_video_path = os.path.join(UPLOAD_FOLDER, secure_filename(user_video.filename))
        user_video.save(user_video_path)
        
        # Süre kontrolü
        audio_duration = get_media_duration(STATIC_AUDIO)
        user_video_duration = get_media_duration(user_video_path)
        
        if user_video_duration > audio_duration:
            os.remove(user_video_path)
            return "Yüklenen video, müzik dosyasından daha uzun olamaz!", 400
        
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
        
        # Kullanıcının videosunu ölçeklendir ve sesini kaldır
        temp_scaled_video = os.path.join(UPLOAD_FOLDER, f"scaled_{int(time.time())}.mp4")
        scale_cmd = [
            'ffmpeg',
            '-i', user_video_path,
            '-vf', f'scale={target_width}:{target_height}:force_original_aspect_ratio=decrease,pad={target_width}:{target_height}:(ow-iw)/2:(oh-ih)/2',
            '-an',  # Sesi kaldır
            '-c:v', 'libx264',
            '-preset', 'medium',
            '-crf', '23',
            temp_scaled_video
        ]
        subprocess.run(scale_cmd, check=True)
        
        # 3 saniyelik siyah video oluştur
        temp_black_video = os.path.join(UPLOAD_FOLDER, f"black_{int(time.time())}.mp4")
        black_cmd = [
            'ffmpeg',
            '-f', 'lavfi',
            '-i', f'color=c=black:s={target_width}x{target_height}:d=3',
            '-c:v', 'libx264',
            '-preset', 'medium',
            '-crf', '23',
            temp_black_video
        ]
        subprocess.run(black_cmd, check=True)
        
        # Birleştirme için çıktı dosyası
        output_path = os.path.join(UPLOAD_FOLDER, f"merged_{int(time.time())}.mp4")
        
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
            "-preset", "medium",
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
    app.run(debug=True, host='0.0.0.0', port=5000)
