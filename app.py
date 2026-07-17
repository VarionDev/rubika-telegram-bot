import os
import requests
import uuid
from flask import Flask, request, jsonify

app = Flask(__name__)

# ================= تنظیمات =================
TG_TOKEN = '8067819715:AAGDbuuq1Tyo7Ar8RiUsBfrRm4lyr0UnbZc'

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
    """آپلود ویدیو در آپارات با لاگ دقیق"""
    try:
        print(f"📤 شروع آپلود در آپارات: {title}")
        
        # مرحله ۱: احراز هویت
        auth_url = "https://www.aparat.com/api/fa/v1/user/authenticate"
        auth_data = {
            "accountname": APARAT_USERNAME,
            "password": APARAT_PASSWORD
        }
        
        print(f"🔐 تلاش برای احراز هویت...")
        auth_res = requests.post(auth_url, data=auth_data, timeout=30)
        print(f"📥 پاسخ خام احراز هویت: {auth_res.text[:500]}")
        
        try:
            auth_json = auth_res.json()
        except Exception as e:
            print(f"❌ خطا در parsing JSON احراز هویت: {e}")
            return None, f"پاسخ نامعتبر از آپارات: {auth_res.text[:200]}"
        
        if "data" not in auth_json or "ltoken" not in auth_json["data"]:
            print(f"❌ خطا در احراز هویت: {auth_json}")
            return None, f"خطا در احراز هویت: {auth_json.get('errors', 'نامشخص')}"
        
        ltoken = auth_json["data"]["ltoken"]
        print(f"✅ احراز هویت موفق")

        # مرحله ۲: آپلود فایل
        upload_url = "https://www.aparat.com/api/fa/v1/video/upload/uploadfile"
        
        print(f"⬆️ شروع آپلود فایل...")
        with open(video_path, 'rb') as f:
            files = {'video': (os.path.basename(video_path), f, 'video/mp4')}
            data = {
                'ltoken': ltoken,
                'title': title,
                'description': description,
                'category': '11'
            }
            upload_res = requests.post(upload_url, files=files, data=data, timeout=600)
        
        print(f"📥 پاسخ خام آپلود: {upload_res.text[:500]}")
        
        try:
            upload_json = upload_res.json()
        except Exception as e:
            print(f"❌ خطا در parsing JSON آپلود: {e}")
            return None, f"پاسخ نامعتبر از آپارات: {upload_res.text[:200]}"
        
        if "data" not in upload_json:
            print(f"❌ خطا در آپلود: {upload_json}")
            return None, f"خطا در آپلود: {upload_json.get('errors', upload_json)}"
        
        video_uid = upload_json["data"]["uid"]
        print(f"✅ ویدیو آپلود شد. UID: {video_uid}")
        
        aparat_link = f"https://www.aparat.com/v/{video_uid}"
        return aparat_link, None
        
    except Exception as e:
        print(f"❌ خطای استثناء: {str(e)}")
        import traceback
        traceback.print_exc()
        return None, str(e)

@app.route('/', methods=['POST'])
def webhook():
    data = request.json
    if not data or 'message' not in data:
        return jsonify({"ok": True})

    msg = data['message']
    chat_id = msg['chat']['id']
    text = msg.get('text', '').strip()

    if text.startswith('http://') or text.startswith('https://'):
        send_tg_message(chat_id, "⏳ در حال دانلود و آپلود...")
        
        filename = f"/tmp/video_{uuid.uuid4().hex}.mp4"
        try:
            print(f"⬇️ شروع دانلود از: {text[:50]}...")
            with requests.get(text, stream=True, timeout=600) as r:
                r.raise_for_status()
                with open(filename, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
            
            file_size = os.path.getsize(filename)
            print(f"✅ دانلود موفق. حجم: {file_size / 1024 / 1024:.1f} MB")
            
            send_tg_message(chat_id, f"⬆️ دانلود شد ({file_size / 1024 / 1024:.1f} MB). در حال آپلود...")
            
            title = f"ویدیو - {uuid.uuid4().hex[:8]}"
            aparat_link, error = upload_to_aparat(filename, title)
            
            if aparat_link:
                send_tg_message(chat_id, f"✅ آپلود موفق!\n\n🔗 {aparat_link}")
            else:
                send_tg_message(chat_id, f"❌ خطا:\n{error}")
                
        except Exception as e:
            send_tg_message(chat_id, f"❌ خطا: {str(e)[:200]}")
        finally:
            if os.path.exists(filename):
                os.remove(filename)
        return jsonify({"ok": True})

    send_tg_message(chat_id, "⚠️ لطفاً لینک مستقیم ویدیو را ارسال کنید.")
    return jsonify({"ok": True})

@app.route('/', methods=['GET'])
def health_check():
    return "Bot is running!", 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
