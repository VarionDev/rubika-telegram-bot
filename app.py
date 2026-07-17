import os
import requests
import uuid
import hashlib
import json
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
        print(f"خطا در ارسال پیام تلگرام: {e}")

def get_aparat_ltoken(username, password):
    """مرحله ۱: لاگین و دریافت ltoken طبق مستندات آپارات"""
    # رمز عبور باید به صورت sha1(MD5(password)) هش شود
    md5_hash = hashlib.md5(password.encode('utf-8')).digest()
    sha1_hash = hashlib.sha1(md5_hash).hexdigest()
    
    login_url = f"https://www.aparat.com/etc/api/login/luser/{username}/lpass/{sha1_hash}"
    print(f"🔐 تلاش برای لاگین در آپارات...")
    
    try:
        res = requests.get(login_url, timeout=30)
        print(f"📥 پاسخ خام لاگین: {res.text[:300]}")
        data = res.json()
        
        # استخراج ltoken از پاسخ (طبق مستندات، در آرایه login یا root قرار دارد)
        if 'login' in data and 'ltoken' in data['login']:
            return data['login']['ltoken']
        elif 'ltoken' in data:
            return data['ltoken']
        else:
            return None, f"خطا در دریافت توکن: {data}"
    except Exception as e:
        return None, str(e)

def get_upload_form(username, ltoken):
    """مرحله ۲: دریافت formAction و frm-id"""
    form_url = f"https://www.aparat.com/etc/api/uploadform/luser/{username}/ltoken/{ltoken}"
    print(f"📝 درخواست فرم آپلود...")
    
    try:
        res = requests.get(form_url, timeout=30)
        print(f"📥 پاسخ خام فرم: {res.text[:300]}")
        data = res.json()
        
        if 'uploadform' in data:
            return data['uploadform']['formAction'], data['uploadform']['frm-id']
        else:
            return None, None, f"خطا در دریافت فرم: {data}"
    except Exception as e:
        return None, None, str(e)

def upload_to_aparat(video_path, title, description="آپلود خودکار توسط ربات"):
    """مرحله ۳: آپلود تکه‌تکه فایل به آپارات"""
    file_handle = None
    try:
        print(f"📤 شروع فرآیند آپلود در آپارات: {title}")
        
        # ۱. دریافت توکن
        ltoken_result = get_aparat_ltoken(APARAT_USERNAME, APARAT_PASSWORD)
        if isinstance(ltoken_result, tuple): # یعنی خطا رخ داده
            return None, ltoken_result[1]
        ltoken = ltoken_result
        print(f"✅ توکن دریافت شد: {ltoken[:10]}...")

        # ۲. دریافت آدرس آپلود
        form_action, frm_id = get_upload_form(APARAT_USERNAME, ltoken)
        if not form_action:
            return None, frm_id # frm_id در اینجا حاوی پیام خطا است
        print(f"✅ آدرس آپلود دریافت شد. frm-id: {frm_id}")

        # ۳. آپلود فایل به صورت Streaming (تکه‌تکه برای جلوگیری از پر شدن رم)
        print(f"⬆️ شروع آپلود تکه‌تکه فایل...")
        file_handle = open(video_path, 'rb')
        
        # فیلدها دقیقاً طبق مستندات آپارات
        fields = {
            'video': (os.path.basename(video_path), file_handle, 'video/mp4'),
            'frm-id': str(frm_id),
            'data[title]': title,
            'data[category]': '11',  # ۱۱ = آموزشی
            'data[comment]': 'yes',
            'data[descr]': description,
            'data[video_pass]': 'false'
        }
        
        encoder = MultipartEncoder(fields=fields)
        
        def callback(monitor):
            if monitor.bytes_read % (10 * 1024 * 1024) < 8192:  # هر ۱۰ مگابایت
                percent = (monitor.bytes_read / monitor.len) * 100
                print(f"📤 پیشرفت آپلود: {percent:.1f}% ({monitor.bytes_read / 1024 / 1024:.1f} MB)")
        
        monitor = MultipartEncoderMonitor(encoder, callback)
        
        headers = {'Content-Type': monitor.content_type}
        upload_res = requests.post(form_action, data=monitor, headers=headers, timeout=1800)
        
        print(f"📥 پاسخ خام آپلود: {upload_res.text[:500]}")
        
        try:
            data = upload_res.json()
            # طبق مستندات، در صورت موفقیت uid برگردانده می‌شود
            if 'uid' in data:
                video_uid = data['uid']
                print(f"✅ ویدیو با موفقیت آپلود شد. UID: {video_uid}")
                return f"https://www.aparat.com/v/{video_uid}", None
            else:
                return None, f"پاسخ نامعتبر از سرور آپارات: {data}"
        except json.JSONDecodeError:
            return None, f"پاسخ JSON نامعتبر از آپارات: {upload_res.text[:200]}"
            
    except Exception as e:
        print(f"❌ خطای استثناء در آپلود: {str(e)}")
        import traceback
        traceback.print_exc()
        return None, str(e)
    finally:
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
        send_tg_message(chat_id, "⏳ لینک دریافت شد. در حال دانلود و آپلود در آپارات...\n(این فرآیند ممکن است ۱۰-۲۰ دقیقه طول بکشد)")
        
        filename = f"/tmp/video_{uuid.uuid4().hex}.mp4"
        try:
            print(f"⬇️ شروع دانلود از لینک...")
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
                                print(f"📥 پیشرفت دانلود: {percent:.1f}%")
            
            file_size = os.path.getsize(filename)
            print(f"✅ دانلود موفق. حجم: {file_size / 1024 / 1024:.1f} MB")
            
            send_tg_message(chat_id, f"⬆️ دانلود انجام شد ({file_size / 1024 / 1024:.1f} MB). در حال آپلود در آپارات...")
            
            title = f"ویدیو آموزشی - {uuid.uuid4().hex[:8]}"
            aparat_link, error = upload_to_aparat(filename, title)
            
            if aparat_link:
                send_tg_message(chat_id, f"✅ آپلود با موفقیت انجام شد!\n\n🔗 لینک استریم (نیم‌بها):\n{aparat_link}")
            else:
                send_tg_message(chat_id, f"❌ خطا در آپلود:\n{error}")
                
        except Exception as e:
            send_tg_message(chat_id, f"❌ خطا در پردازش: {str(e)[:200]}")
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
