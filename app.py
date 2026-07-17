import os
import requests
import uuid
from requests_toolbelt import MultipartEncoder, MultipartEncoderMonitor
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

def create_streaming_encoder(file_path, fields):
    """ساخت encoder برای آپلود تکه‌تکه (بدون پر کردن رم)"""
    # باز کردن فایل
    file_handle = open(file_path, 'rb')
    
    # ساخت فیلدهای multipart
    multipart_fields = list(fields.items())
    multipart_fields.append(
        ('video', (os.path.basename(file_path), file_handle, 'video/mp4'))
    )
    
    encoder = MultipartEncoder(fields=multipart_fields)
    
    # مانیتور برای نمایش پیشرفت (اختیاری)
    def callback(monitor):
        if monitor.bytes_read % (10 * 1024 * 1024) < 8192:  # هر ۱۰ مگابایت
            percent = (monitor.bytes_read / monitor.len) * 100
            print(f"📤 آپلود: {percent:.1f}% ({monitor.bytes_read / 1024 / 1024:.1f} MB)")
    
    monitor = MultipartEncoderMonitor(encoder, callback)
    return monitor, file_handle

def upload_to_aparat(video_path, title, description="آپلود خودکار توسط ربات"):
    """آپلود ویدیو در آپارات با Streaming Upload"""
    file_handle = None
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
        
        try:
            auth_json = auth_res.json()
        except:
            return None, f"پاسخ نامعتبر از آپارات: {auth_res.text[:200]}"
        
        if "data" not in auth_json or "ltoken" not in auth_json["data"]:
            return None, f"خطا در احراز هویت: {auth_json.get('errors', 'نامشخص')}"
        
        ltoken = auth_json["data"]["ltoken"]
        print(f"✅ احراز هویت موفق")

        # مرحله ۲: آپلود فایل به صورت Streaming (تکه‌تکه)
        upload_url = "https://www.aparat.com/api/fa/v1/video/upload/uploadfile"
        
        fields = {
            'ltoken': ltoken,
            'title': title,
            'description': description,
            'category': '11'
        }
        
        print(f"⬆️ شروع آپلود تکه‌تکه (Streaming)...")
        monitor, file_handle = create_streaming_encoder(video_path, fields)
        
        upload_res = requests.post(
            upload_url, 
            data=monitor, 
            headers={'Content-Type': monitor.content_type},
            timeout=1800  # ۳۰ دقیقه زمان برای آپلود
        )
        
        print(f"📥 پاسخ آپلود: {upload_res.text[:300]}")
        
        try:
            upload_json = upload_res.json()
        except:
            return None, f"پاسخ نامعتبر: {upload_res.text[:200]}"
        
        if "data" not in upload_json:
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
    finally:
        # بستن فایل در هر حالت
        if file_handle:
            file_handle.close()

@app.route('/', methods=['POST'])
def webhook():
    data = request.json
    if not data or 'message' not in data:
        return jsonify({"ok": True})

    msg = data['message']
    chat_id = msg['chat']['id']
    text = msg.get('text', '').strip()

    if text.startswith('http://') or text.startswith('https://'):
        send_tg_message(chat_id, "⏳ در حال دانلود و آپلود...\n(ممکن است ۱۰-۲۰ دقیقه طول بکشد)")
        
        filename = f"/tmp/video_{uuid.uuid4().hex}.mp4"
        try:
            print(f"⬇️ شروع دانلود از: {text[:50]}...")
            
            # دانلود به صورت Streaming (تکه‌تکه)
            with requests.get(text, stream=True, timeout=1800) as r:
                r.raise_for_status()
                total_size = int(r.headers.get('content-length', 0))
                downloaded = 0
                
                with open(filename, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)
                            if total_size > 0 and downloaded % (10 * 1024 * 1024) < 8192:
                                percent = (downloaded / total_size) * 100
                                print(f"📥 دانلود: {percent:.1f}%")
            
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
