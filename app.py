import os
import requests
import uuid
from flask import Flask, request, jsonify

app = Flask(__name__)

# ================= تنظیمات =================
TG_TOKEN = '8067819715:AAGDbuuq1Tyo7Ar8RiUsBfrRm4lyr0UnbZc'

# ⚠️ اطلاعات آپارات خود را اینجا وارد کنید
APARAT_USERNAME = os.environ.get('APARAT_USERNAME', 'mataleb_darsi')
APARAT_PASSWORD = os.environ.get('APARAT_PASSWORD', 'abolfazl')
# ============================================

def send_tg_message(chat_id, text):
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    try:
        requests.post(url, json={"chat_id": chat_id, "text": text}, timeout=10)
    except Exception as e:
        print(f"خطا در ارسال پیام: {e}")

def upload_to_aparat(video_path, title, description="آپلود خودکار توسط ربات"):
    """آپلود ویدیو در آپارات"""
    try:
        print(f"📤 شروع آپلود در آپارات: {title}")
        
        # مرحله ۱: احراز هویت
        auth_url = "https://www.aparat.com/api/fa/v1/user/authenticate"
        auth_data = {
            "accountname": APARAT_USERNAME,
            "password": APARAT_PASSWORD
        }
        auth_res = requests.post(auth_url, data=auth_data, timeout=30).json()
        
        if "data" not in auth_res or "ltoken" not in auth_res["data"]:
            print(f"❌ خطا در احراز هویت آپارات: {auth_res}")
            return None, "خطا در احراز هویت آپارات"
        
        ltoken = auth_res["data"]["ltoken"]
        print(f"✅ احراز هویت موفق")

        # مرحله ۲: آپلود فایل
        upload_url = "https://www.aparat.com/api/fa/v1/video/upload/uploadfile"
        with open(video_path, 'rb') as f:
            files = {'video': (os.path.basename(video_path), f, 'video/mp4')}
            data = {
                'ltoken': ltoken,
                'title': title,
                'description': description,
                'category': '11'  # دسته‌بندی: آموزشی
            }
            print(f"⬆️ در حال آپلود فایل...")
            res = requests.post(upload_url, files=files, data=data, timeout=600).json()
        
        if "data" not in res:
            print(f"❌ خطا در آپلود: {res}")
            return None, f"خطا در آپلود: {res.get('errors', 'نامشخص')}"
        
        video_uid = res["data"]["uid"]
        video_hash = res["data"].get("hash", "")
        print(f"✅ ویدیو آپلود شد. UID: {video_uid}")
        
        # مرحله ۳: دریافت لینک استریم
        aparat_link = f"https://www.aparat.com/v/{video_uid}"
        return aparat_link, None
        
    except Exception as e:
        print(f"❌ خطا در آپلود آپارات: {str(e)}")
        return None, str(e)

@app.route('/', methods=['POST'])
def webhook():
    data = request.json
    if not data or 'message' not in data:
        return jsonify({"ok": True})

    msg = data['message']
    chat_id = msg['chat']['id']
    text = msg.get('text', '').strip()

    # بررسی لینک مستقیم
    if text.startswith('http://') or text.startswith('https://'):
        send_tg_message(chat_id, "⏳ لینک دریافت شد. در حال دانلود و آپلود در آپارات...\n(این فرآیند ممکن است ۵-۱۰ دقیقه طول بکشد)")
        
        filename = f"/tmp/video_{uuid.uuid4().hex}.mp4"
        try:
            # دانلود ویدیو به صورت Streaming
            print(f"⬇️ شروع دانلود از: {text[:50]}...")
            with requests.get(text, stream=True, timeout=600) as r:
                r.raise_for_status()
                total_size = int(r.headers.get('content-length', 0))
                downloaded = 0
                
                with open(filename, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)
                            if total_size > 0:
                                percent = (downloaded / total_size) * 100
                                if downloaded % (10 * 1024 * 1024) < 8192:  # هر ۱۰ مگابایت
                                    print(f"📥 دانلود: {percent:.1f}%")
            
            file_size = os.path.getsize(filename)
            print(f"✅ دانلود موفق. حجم: {file_size / 1024 / 1024:.1f} مگابایت")
            
            send_tg_message(chat_id, f"⬆️ دانلود انجام شد ({file_size / 1024 / 1024:.1f} MB). در حال آپلود در آپارات...")
            
            # آپلود در آپارات
            title = f"ویدیو - {uuid.uuid4().hex[:8]}"
            aparat_link, error = upload_to_aparat(filename, title)
            
            if aparat_link:
                send_tg_message(chat_id, f"✅ ویدیو با موفقیت آپلود شد!\n\n🔗 لینک استریم:\n{aparat_link}")
            else:
                send_tg_message(chat_id, f"❌ خطا در آپلود در آپارات:\n{error}")
                
        except Exception as e:
            send_tg_message(chat_id, f"❌ خطا: {str(e)[:200]}")
        finally:
            if os.path.exists(filename):
                os.remove(filename)
        return jsonify({"ok": True})

    # اگر لینک نبود
    send_tg_message(chat_id, "⚠️ لطفاً لینک مستقیم ویدیو را ارسال کنید.")
    return jsonify({"ok": True})

@app.route('/', methods=['GET'])
def health_check():
    return "Bot is running!", 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
