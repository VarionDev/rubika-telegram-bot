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

# لیست update_id های پردازش شده (برای جلوگیری از تکرار)
processed_updates = set()
# =================================================

def send_tg_message(chat_id, text):
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    try:
        requests.post(url, json={"chat_id": chat_id, "text": text}, timeout=10)
    except:
        pass

def upload_to_rubika(file_path, caption):
    """فرآیند ۳ مرحله‌ای آپلود فایل در روبیکا"""
    ext = os.path.splitext(file_path)[1].lower().replace('.', '')
    file_type = "File"
    if ext in ['jpg', 'jpeg', 'png', 'webp', 'gif']: file_type = "Image"
    elif ext in ['mp4', 'mkv', 'avi', 'webm', 'mov']: file_type = "Video"
    elif ext in ['mp3', 'wav', 'm4a']: file_type = "Audio"
    elif ext in ['ogg']: file_type = "Voice"

    try:
        # مرحله ۱: درخواست آدرس آپلود
        req_url = f"https://botapi.rubika.ir/v3/{RUBIKA_TOKEN}/requestSendFile"
        res1 = requests.post(req_url, json={"type": file_type}, headers={"Content-Type": "application/json"}, timeout=30).json()
        if "data" not in res1 or "upload_url" not in res1["data"]:
            print(f"❌ خطا در مرحله ۱ روبیکا: {res1}")
            return False
        upload_url = res1["data"]["upload_url"]

        # مرحله ۲: آپلود فایل
        with open(file_path, 'rb') as f:
            files = {'file': (os.path.basename(file_path), f)}
            res2 = requests.post(upload_url, files=files, timeout=300).json()
            if "data" not in res2 or "file_id" not in res2["data"]:
                print(f"❌ خطا در مرحله ۲ روبیکا: {res2}")
                return False
        new_file_id = res2["data"]["file_id"]

        # مرحله ۳: ارسال به چت
        send_url = f"https://botapi.rubika.ir/v3/{RUBIKA_TOKEN}/sendFile"
        res3 = requests.post(send_url, json={
            "chat_id": TARGET_CHAT_ID,
            "file_id": new_file_id,
            "text": caption
        }, headers={"Content-Type": "application/json"}, timeout=30).json()
        
        print(f"✅ آپلود در روبیکا موفق بود: {res3}")
        return res3.get("status") == "OK"
    except Exception as e:
        print(f"❌ خطا در آپلود روبیکا: {str(e)}")
        return False

@app.route('/', methods=['POST'])
def webhook():
    data = request.json
    if not data or 'message' not in data:
        return jsonify({"ok": True})

    # ⭐ جلوگیری از پردازش تکراری
    update_id = data.get('update_id')
    if update_id in processed_updates:
        print(f"⚠️ Update {update_id} قبلاً پردازش شده. نادیده گرفته شد.")
        return jsonify({"ok": True})
    
    processed_updates.add(update_id)
    
    # محدود کردن اندازه لیست (برای جلوگیری از پر شدن حافظه)
    if len(processed_updates) > 1000:
        processed_updates.clear()

    msg = data['message']
    chat_id = msg['chat']['id']
    text = msg.get('text', '').strip()
    temp_dir = "/tmp"

    print(f"📩 پیام جدید از {chat_id}: {text[:50]}...")

    # ================= ۱. بررسی لینک یوتیوب =================
    if 'youtube.com' in text or 'youtu.be' in text:
        send_tg_message(chat_id, "⏳ در حال دانلود از یوتیوب... (ممکن است کمی طول بکشد)")
        filename = os.path.join(temp_dir, f"yt_{uuid.uuid4().hex}.mp4")
        
        ydl_opts = {
            'format': 'best[height<=720]',
            'outtmpl': filename,
            'noplaylist': True,
            'quiet': True,
        }
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([text])
            
            send_tg_message(chat_id, "⬆️ دانلود انجام شد. در حال ارسال به روبیکا...")
            if upload_to_rubika(filename, "📥 دانلود از یوتیوب"):
                send_tg_message(chat_id, "✅ ویدیو یوتیوب با موفقیت ارسال شد!")
            else:
                send_tg_message(chat_id, "❌ خطا در آپلود در روبیکا.")
        except Exception as e:
            send_tg_message(chat_id, f"❌ خطا در دانلود یوتیوب.\n{str(e)[:100]}")
        finally:
            if os.path.exists(filename):
                os.remove(filename)
        return jsonify({"ok": True})

    # ================= ۲. بررسی لینک مستقیم / عمومی =================
    if text.startswith('http://') or text.startswith('https://'):
        send_tg_message(chat_id, "⏳ در حال دانلود از لینک...")
        
        filename = os.path.join(temp_dir, f"dl_{uuid.uuid4().hex}")
        try:
            with requests.get(text, stream=True, timeout=300) as r:
                r.raise_for_status()
                if 'content-disposition' in r.headers:
                    cd = r.headers['content-disposition']
                    if 'filename=' in cd:
                        fname = cd.split('filename=')[1].strip('"\'')
                        filename = os.path.join(temp_dir, fname)
                
                with open(filename, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        f.write(chunk)
            
            file_size = os.path.getsize(filename)
            print(f"✅ دانلود موفق. حجم: {file_size} بایت")
            
            send_tg_message(chat_id, "⬆️ دانلود انجام شد. در حال ارسال به روبیکا...")
            if upload_to_rubika(filename, "📤 انتقال از لینک"):
                send_tg_message(chat_id, "✅ فایل با موفقیت ارسال شد!")
            else:
                send_tg_message(chat_id, "❌ خطا در آپلود در روبیکا.")
        except Exception as e:
            send_tg_message(chat_id, f"❌ خطا در دانلود لینک.\n{str(e)[:100]}")
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
                "💡 راه‌حل: لینک مستقیم دانلود این فایل را برای من بفرستید.")
            return jsonify({"ok": True})

        send_tg_message(chat_id, "⏳ در حال دریافت فایل و انتقال به روبیکا...")
        
        file_req = requests.get(f"https://api.telegram.org/bot{TG_TOKEN}/getFile?file_id={file_info['file_id']}", timeout=30).json()
        if not file_req.get('ok'):
            send_tg_message(chat_id, "❌ خطا در دریافت اطلاعات فایل از تلگرام.")
            return jsonify({"ok": True})
            
        download_url = f"https://api.telegram.org/file/bot{TG_TOKEN}/{file_req['result']['file_path']}"
        temp_file = os.path.join(temp_dir, file_name)
        
        try:
            with requests.get(download_url, stream=True, timeout=120) as r:
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
            send_tg_message(chat_id, f"❌ خطا در پردازش فایل: {str(e)[:100]}")
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
