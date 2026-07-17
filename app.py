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

PROCESSED_FILE = 'processed_ids.txt'
# =================================================

def is_processed(update_id):
    """بررسی می‌کند آیا این پیام قبلاً پردازش شده است یا خیر"""
    if not os.path.exists(PROCESSED_FILE):
        return False
    with open(PROCESSED_FILE, 'r') as f:
        return str(update_id) in f.read()

def mark_as_processed(update_id):
    """شناسه پیام را در فایل ذخیره می‌کند"""
    with open(PROCESSED_FILE, 'a') as f:
        f.write(f"{update_id}\n")
    
    # پاک‌سازی فایل اگر خیلی بزرگ شد (نگه‌داری ۵۰۰ تای آخر)
    if os.path.getsize(PROCESSED_FILE) > 10000:
        with open(PROCESSED_FILE, 'r') as f:
            lines = f.readlines()
        with open(PROCESSED_FILE, 'w') as f:
            f.writelines(lines[-500:])

def send_tg_message(chat_id, text):
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    try:
        requests.post(url, json={"chat_id": chat_id, "text": text}, timeout=10)
    except Exception as e:
        print(f"خطا در ارسال پیام تلگرام: {e}")

def upload_to_rubika(file_path, caption):
    """فرآیند ۳ مرحله‌ای آپلود فایل در روبیکا"""
    ext = os.path.splitext(file_path)[1].lower().replace('.', '')
    file_type = "File"
    if ext in ['jpg', 'jpeg', 'png', 'webp', 'gif']: file_type = "Image"
    elif ext in ['mp4', 'mkv', 'avi', 'webm', 'mov']: file_type = "Video"
    elif ext in ['mp3', 'wav', 'm4a']: file_type = "Audio"
    elif ext in ['ogg']: file_type = "Voice"

    try:
        print(f"📤 شروع آپلود در روبیکا | نوع: {file_type}")
        
        # مرحله ۱
        req_url = f"https://botapi.rubika.ir/v3/{RUBIKA_TOKEN}/requestSendFile"
        res1 = requests.post(req_url, json={"type": file_type}, headers={"Content-Type": "application/json"}, timeout=30).json()
        if "data" not in res1 or "upload_url" not in res1["data"]:
            print(f"❌ خطای روبیکا مرحله ۱: {res1}")
            return False
        upload_url = res1["data"]["upload_url"]

        # مرحله ۲
        with open(file_path, 'rb') as f:
            files = {'file': (os.path.basename(file_path), f)}
            res2 = requests.post(upload_url, files=files, timeout=300).json()
            if "data" not in res2 or "file_id" not in res2["data"]:
                print(f"❌ خطای روبیکا مرحله ۲: {res2}")
                return False
        new_file_id = res2["data"]["file_id"]
        print(f"✅ فایل آپلود شد. File ID: {new_file_id}")

        # مرحله ۳
        send_url = f"https://botapi.rubika.ir/v3/{RUBIKA_TOKEN}/sendFile"
        res3 = requests.post(send_url, json={
            "chat_id": TARGET_CHAT_ID,
            "file_id": new_file_id,
            "text": caption
        }, headers={"Content-Type": "application/json"}, timeout=30).json()
        
        print(f"✅ نتیجه نهایی روبیکا: {res3}")
        return res3.get("status") == "OK"
        
    except Exception as e:
        print(f"❌ خطای استثناء در آپلود روبیکا: {str(e)}")
        return False

@app.route('/', methods=['POST'])
def webhook():
    data = request.json
    if not data or 'message' not in data:
        return jsonify({"ok": True})

    update_id = data.get('update_id')
    
    # ⭐ بررسی تکراری بودن با استفاده از فایل (مقاوم در برابر ری‌استارت)
    if is_processed(update_id):
        print(f"⚠️ پیام تکراری (Update ID: {update_id}) نادیده گرفته شد.")
        return jsonify({"ok": True})
    
    # ثبت پیام به عنوان پردازش‌شده
    mark_as_processed(update_id)

    msg = data['message']
    chat_id = msg['chat']['id']
    text = msg.get('text', '').strip()
    temp_dir = "/tmp"

    print(f"📩 پیام جدید دریافت شد | Update ID: {update_id} | متن: {text[:50]}")

    # ================= ۱. بررسی لینک یوتیوب =================
    if 'youtube.com' in text or 'youtu.be' in text:
        send_tg_message(chat_id, "⏳ در حال دانلود از یوتیوب...")
        filename = os.path.join(temp_dir, f"yt_{uuid.uuid4().hex}.mp4")
        
        ydl_opts = {'format': 'best[height<=720]', 'outtmpl': filename, 'noplaylist': True, 'quiet': True}
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([text])
            
            send_tg_message(chat_id, "⬆️ دانلود شد. در حال ارسال به روبیکا...")
            if upload_to_rubika(filename, "📥 دانلود از یوتیوب"):
                send_tg_message(chat_id, "✅ با موفقیت ارسال شد!")
            else:
                send_tg_message(chat_id, "❌ خطا در آپلود روبیکا.")
        except Exception as e:
            send_tg_message(chat_id, f"❌ خطا در یوتیوب: {str(e)[:100]}")
        finally:
            if os.path.exists(filename): os.remove(filename)
        return jsonify({"ok": True})

    # ================= ۲. بررسی لینک مستقیم =================
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
            print(f"✅ دانلود لینک موفق. حجم: {file_size} بایت")
            
            send_tg_message(chat_id, "⬆️ دانلود شد. در حال ارسال به روبیکا...")
            if upload_to_rubika(filename, "📤 انتقال از لینک"):
                send_tg_message(chat_id, "✅ فایل با موفقیت ارسال شد!")
            else:
                send_tg_message(chat_id, "❌ خطا در آپلود روبیکا. (احتمالاً حجم فایل برای روبیکا زیاد است)")
        except Exception as e:
            send_tg_message(chat_id, f"❌ خطا در دانلود لینک: {str(e)[:100]}")
        finally:
            if os.path.exists(filename): os.remove(filename)
        return jsonify({"ok": True})

    # ================= ۳. فایل‌های تلگرام =================
    file_info = None
    file_name = "unknown_file"
    
    if 'document' in msg:
        file_info = msg['document']
        file_name = msg['document'].get('file_name', f"doc_{uuid.uuid4().hex}.pdf")
    elif 'video' in msg:
        file_info = msg['video']
        file_name = f"vid_{uuid.uuid4().hex}.mp4"
    elif 'photo' in msg:
        file_info = msg['photo'][-1]
        file_name = f"photo_{uuid.uuid4().hex}.jpg"

    if file_info:
        file_size = file_info.get('file_size', 0)
        if file_size > 20 * 1024 * 1024:
            send_tg_message(chat_id, "⚠️ فایل بالای ۲۰ مگابایت است. لطفاً لینک مستقیم آن را بفرستید.")
            return jsonify({"ok": True})

        send_tg_message(chat_id, "⏳ در حال دریافت و انتقال...")
        file_req = requests.get(f"https://api.telegram.org/bot{TG_TOKEN}/getFile?file_id={file_info['file_id']}", timeout=30).json()
        
        if file_req.get('ok'):
            download_url = f"https://api.telegram.org/file/bot{TG_TOKEN}/{file_req['result']['file_path']}"
            temp_file = os.path.join(temp_dir, file_name)
            try:
                with requests.get(download_url, stream=True, timeout=120) as r:
                    r.raise_for_status()
                    with open(temp_file, 'wb') as f:
                        for chunk in r.iter_content(chunk_size=8192):
                            f.write(chunk)
                
                send_tg_message(chat_id, "⬆️ در حال آپلود در روبیکا...")
                if upload_to_rubika(temp_file, "📤 انتقال از تلگرام"):
                    send_tg_message(chat_id, "✅ انتقال موفق!")
                else:
                    send_tg_message(chat_id, "❌ خطا در آپلود روبیکا.")
            except Exception as e:
                send_tg_message(chat_id, f"❌ خطا: {str(e)[:100]}")
            finally:
                if os.path.exists(temp_file): os.remove(temp_file)
                
    return jsonify({"ok": True})

@app.route('/', methods=['GET'])
def health_check():
    return "Bot is running!", 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
