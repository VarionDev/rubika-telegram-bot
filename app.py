import os
import requests
import uuid
import yt_dlp
from flask import Flask, request, jsonify

app = Flask(__name__)

# ================= تنظیمات ربات =================
TG_TOKEN = '8067819715:AAGDbuuq1Tyo7Ar8RiUsBfrRm4lyr0UnbZc'
RUBIKA_TOKEN = 'BAIEEA0ZEUKDUUKNLZQPYCWNPMZEDMIFZLLIHEANSFYNIGCXPBFBTHMFTIWEXKXV'
TARGET_CHAT_ID = 'b0B2cLU04Ii0a60aed438e58d49b5bb5'
# =================================================

def send_tg_message(chat_id, text):
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": chat_id, "text": text})

def upload_to_rubika(file_path, caption):
    """فرآیند ۳ مرحله‌ای آپلود فایل در روبیکا"""
    ext = os.path.splitext(file_path)[1].lower().replace('.', '')
    file_type = "File"
    if ext in ['jpg', 'jpeg', 'png', 'webp', 'gif']: file_type = "Image"
    elif ext in ['mp4', 'mkv', 'avi', 'webm', 'mov']: file_type = "Video"
    elif ext in ['mp3', 'wav', 'm4a']: file_type = "Audio"
    elif ext in ['ogg']: file_type = "Voice"

    # مرحله ۱: درخواست آدرس آپلود
    req_url = f"https://botapi.rubika.ir/v3/{RUBIKA_TOKEN}/requestSendFile"
    res1 = requests.post(req_url, json={"type": file_type}, headers={"Content-Type": "application/json"}).json()
    if "data" not in res1 or "upload_url" not in res1["data"]:
        return False
    upload_url = res1["data"]["upload_url"]

    # مرحله ۲: آپلود فایل
    try:
        with open(file_path, 'rb') as f:
            files = {'file': (os.path.basename(file_path), f)}
            res2 = requests.post(upload_url, files=files, timeout=300).json()
            if "data" not in res2 or "file_id" not in res2["data"]:
                return False
        new_file_id = res2["data"]["file_id"]
    except Exception:
        return False

    # مرحله ۳: ارسال به چت
    send_url = f"https://botapi.rubika.ir/v3/{RUBIKA_TOKEN}/sendFile"
    res3 = requests.post(send_url, json={
        "chat_id": TARGET_CHAT_ID,
        "file_id": new_file_id,
        "text": caption
    }, headers={"Content-Type": "application/json"}).json()
    
    return res3.get("status") == "OK"

@app.route('/', methods=['POST'])
def webhook():
    data = request.json
    if not data or 'message' not in data:
        return jsonify({"ok": True})

    msg = data['message']
    chat_id = msg['chat']['id']
    text = msg.get('text', '').strip()
    temp_dir = "/tmp"

    # ================= ۱. بررسی لینک یوتیوب =================
    if 'youtube.com' in text or 'youtu.be' in text:
        send_tg_message(chat_id, "⏳ در حال دانلود از یوتیوب... (ممکن است کمی طول بکشد)")
        filename = os.path.join(temp_dir, f"yt_{uuid.uuid4().hex}.mp4")
        
        ydl_opts = {
            'format': 'best[height<=720]', # دانلود با کیفیت حداکثر 720p برای سرعت و پایداری بیشتر
            'outtmpl': filename,
            'noplaylist': True,
        }
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([text])
            
            send_tg_message(chat_id, "⬆️ دانلود انجام شد. در حال ارسال به روبیکا...")
            if upload_to_rubika(filename, f"📥 دانلود از یوتیوب:\n{text}"):
                send_tg_message(chat_id, "✅ ویدیو یوتیوب با موفقیت ارسال شد!")
            else:
                send_tg_message(chat_id, "❌ خطا در آپلود در روبیکا.")
        except Exception as e:
            send_tg_message(chat_id, f"❌ خطا در دانلود یوتیوب. (لینک را چک کنید)\n{str(e)}")
        finally:
            if os.path.exists(filename):
                os.remove(filename)
        return jsonify({"ok": True})

    # ================= ۲. بررسی لینک مستقیم / عمومی =================
    if text.startswith('http://') or text.startswith('https://'):
        send_tg_message(chat_id, "⏳ در حال دانلود از لینک...")
        
        # تلاش برای پیدا کردن نام فایل از هدرها یا URL
        filename = os.path.join(temp_dir, f"dl_{uuid.uuid4().hex}")
        try:
            with requests.get(text, stream=True, timeout=300) as r:
                r.raise_for_status()
                # اگر سرور نام فایل را فرستاد، از آن استفاده کن
                if 'content-disposition' in r.headers:
                    cd = r.headers['content-disposition']
                    if 'filename=' in cd:
                        fname = cd.split('filename=')[1].strip('"\'')
                        filename = os.path.join(temp_dir, fname)
                
                with open(filename, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        f.write(chunk)
            
            send_tg_message(chat_id, "⬆️ دانلود انجام شد. در حال ارسال به روبیکا...")
            if upload_to_rubika(filename, "📤 انتقال از لینک مستقیم/عمومی"):
                send_tg_message(chat_id, "✅ فایل با موفقیت ارسال شد!")
            else:
                send_tg_message(chat_id, "❌ خطا در آپلود در روبیکا.")
        except Exception as e:
            send_tg_message(chat_id, f"❌ خطا در دانلود لینک. مطمئن شوید لینک مستقیم و عمومی است.\n{str(e)}")
        finally:
            if os.path.exists(filename):
                os.remove(filename)
        return jsonify({"ok": True})

    # ================= ۳. بررسی فایل‌های معمولی تلگرام =================
    file_info = None
    file_name = "unknown_file"
    
    if 'document' in msg:
        file_info = msg['document']
        file_name = msg['document'].get('file_name', f"doc_{uuid.uuid4().hex}.pdf")
    elif 'video' in msg:
        file_info = msg['video']
        file_name = f"vid_{uuid.uuid4().hex}.mp4"
    elif 'audio' in msg:
        file_info = msg['audio']
        file_name = f"aud_{uuid.uuid4().hex}.mp3"
    elif 'voice' in msg:
        file_info = msg['voice']
        file_name = f"voice_{uuid.uuid4().hex}.ogg"
    elif 'photo' in msg:
        file_info = msg['photo'][-1]
        file_name = f"photo_{uuid.uuid4().hex}.jpg"

    if file_info:
        file_size = file_info.get('file_size', 0)
        
        if file_size > 20 * 1024 * 1024:
            send_tg_message(chat_id, 
                f"⚠️ این فایل {round(file_size/1024/1024, 1)} مگابایت است.\n\n"
                "🤖 API رسمی تلگرام به ربات‌ها اجازه دانلود فایل‌های بالای ۲۰ مگابایت را نمی‌دهد.\n\n"
                "💡 راه‌حل: لینک مستقیم دانلود این فایل را برای من بفرستید تا آن را انتقال دهم.")
            return jsonify({"ok": True})

        send_tg_message(chat_id, "⏳ در حال دریافت فایل و انتقال به روبیکا...")
        
        file_req = requests.get(f"https://api.telegram.org/bot{TG_TOKEN}/getFile?file_id={file_info['file_id']}").json()
        if not file_req.get('ok'):
            send_tg_message(chat_id, "❌ خطا در دریافت اطلاعات فایل از تلگرام.")
            return jsonify({"ok": True})
            
        download_url = f"https://api.telegram.org/file/bot{TG_TOKEN}/{file_req['result']['file_path']}"
        temp_file = os.path.join(temp_dir, file_name)
        
        try:
            with requests.get(download_url, stream=True) as r:
                r.raise_for_status()
                with open(temp_file, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        f.write(chunk)
            
            send_tg_message(chat_id, "⬆️ فایل دریافت شد. در حال آپلود در روبیکا...")
            if upload_to_rubika(temp_file, "📤 انتقال از تلگرام"):
                send_tg_message(chat_id, "✅ انتقال با موفقیت انجام شد!")
            else:
                send_tg_message(chat_id, "❌ خطا در آپلود فایل در سرور روبیکا.")
        except Exception as e:
            send_tg_message(chat_id, f"❌ خطا در پردازش فایل: {str(e)}")
        finally:
            if os.path.exists(temp_file):
                os.remove(temp_file)
                
    return jsonify({"ok": True})

@app.route('/', methods=['GET'])
def health_check():
    return "Bot is running!", 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
