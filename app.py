import os
import requests
import uuid
import hashlib
import json
from flask import Flask, request, jsonify

app = Flask(__name__)

# ================= تنظیمات =================
TG_TOKEN = '8067819715:AAGDbuuq1Tyo7Ar8RiUsBfrRm4lyr0UnbZc'

APARAT_USERNAME = os.environ.get('APARAT_USERNAME')
APARAT_PASSWORD = os.environ.get('APARAT_PASSWORD')

if not APARAT_USERNAME or not APARAT_PASSWORD:
    print("❌ خطای بحرانی: نام کاربری یا رمز عبور آپارات در Environment Variables تنظیم نشده است!")

# هدرهای قوی‌تر برای عبور از فایروال‌های اولیه
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'fa-IR,fa;q=0.9,en-US;q=0.8,en;q=0.7',
    'Connection': 'keep-alive',
    'Cache-Control': 'no-cache'
}
# ============================================

def send_tg_message(chat_id, text):
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    try:
        requests.post(url, json={"chat_id": chat_id, "text": text}, timeout=10)
    except Exception as e:
        print(f"خطا در ارسال پیام تلگرام: {e}")

def _hash_password(password: str) -> str:
    md5_hash = hashlib.md5(password.encode('utf-8')).hexdigest()
    sha1_hash = hashlib.sha1(md5_hash.encode('utf-8')).hexdigest()
    return sha1_hash

def safe_json_response(res, step_name):
    """تابع کمکی برای جلوگیری از خطای JSONDecodeError و نمایش متن خام"""
    if res.status_code != 200:
        return None, f"خطای HTTP {res.status_code} در {step_name}. متن پاسخ: {res.text[:300]}"
    try:
        return res.json(), None
    except json.JSONDecodeError:
        return None, f"پاسخ غیر JSON در {step_name}. متن خام سرور: {res.text[:400]}"

def upload_to_aparat(video_path: str, title: str, description: str = "آپلود خودکار"):
    try:
        print(f"📤 شروع فرآیند آپلود: {title}")
        print(f"🔍 بررسی متغیرها: Username={APARAT_USERNAME}, Password={'*' * len(APARAT_PASSWORD) if APARAT_PASSWORD else 'None'}")
        
        # ۱. لاگین
        hashed_pass = _hash_password(APARAT_PASSWORD)
        login_url = f"https://www.aparat.com/etc/api/login/luser/{APARAT_USERNAME}/lpass/{hashed_pass}"
        print(f"🔐 درخواست لاگین به: {login_url}")
        
        res_login = requests.get(login_url, headers=HEADERS, timeout=30)
        data_login, error = safe_json_response(res_login, "مرحله لاگین")
        if error:
            return None, error
            
        if 'login' not in data_login or 'ltoken' not in data_login['login']:
            return None, f"پاسخ نامعتبر از لاگین: {data_login}"
            
        ltoken = data_login['login']['ltoken']
        print(f"✅ توکن دریافت شد: {ltoken[:10]}...")

        # ۲. دریافت فرم آپلود
        form_url = f"https://www.aparat.com/etc/api/uploadform/luser/{APARAT_USERNAME}/ltoken/{ltoken}"
        print(f"📝 درخواست فرم آپلود...")
        
        res_form = requests.get(form_url, headers=HEADERS, timeout=30)
        data_form, error = safe_json_response(res_form, "مرحله دریافت فرم")
        if error:
            return None, error
            
        if 'uploadform' not in data_form or 'formAction' not in data_form['uploadform']:
            return None, f"پاسخ نامعتبر از فرم: {data_form}"
            
        form_action = data_form['uploadform']['formAction']
        frm_id = data_form['uploadform']['frm-id']
        print(f"✅ آدرس آپلود دریافت شد. frm-id: {frm_id}")

        # ۳. آپلود فایل
        print(f"⬆️ شروع آپلود تکه‌تکه (Streaming) به: {form_action}")
        file_handle = open(video_path, 'rb')
        
        files = {'video': (os.path.basename(video_path), file_handle, 'video/mp4')}
        data = {
            'frm-id': str(frm_id),
            'data[title]': title,
            'data[category]': '11',
            'data[comment]': 'yes',
            'data[descr]': description,
            'data[video_pass]': 'false'
        }
        
        upload_res = requests.post(form_action, files=files, data=data, headers=HEADERS, timeout=1800)
        
        # بررسی پاسخ آپلود
        if upload_res.status_code != 200:
            return None, f"خطای HTTP {upload_res.status_code} در آپلود. متن: {upload_res.text[:300]}"
            
        try:
            data_upload = upload_res.json()
            if 'uploadpost' in data_upload and 'uid' in data_upload['uploadpost']:
                video_uid = data_upload['uploadpost']['uid']
                print(f"✅ ویدیو با موفقیت آپلود شد. UID: {video_uid}")
                return f"https://www.aparat.com/v/{video_uid}", None
            else:
                return None, f"پاسخ نامعتبر (uid یافت نشد): {data_upload}"
        except json.JSONDecodeError:
            return None, f"پاسخ JSON نامعتبر در آپلود. متن خام: {upload_res.text[:400]}"
            
    except Exception as e:
        print(f"❌ خطای استثناء: {str(e)}")
        import traceback
        traceback.print_exc()
        return None, str(e)
    finally:
        if 'file_handle' in locals() and file_handle:
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
        send_tg_message(chat_id, "⏳ لینک دریافت شد. در حال دانلود و آپلود در آپارات...")
        
        filename = f"/tmp/video_{uuid.uuid4().hex}.mp4"
        try:
            print(f"⬇️ شروع دانلود از لینک...")
            with requests.get(text, stream=True, timeout=1800) as r:
                r.raise_for_status()
                with open(filename, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
            
            file_size = os.path.getsize(filename)
            print(f"✅ دانلود موفق. حجم: {file_size / 1024 / 1024:.1f} MB")
            
            send_tg_message(chat_id, f"⬆️ دانلود انجام شد ({file_size / 1024 / 1024:.1f} MB). در حال آپلود...")
            
            title = f"ویدیو آموزشی - {uuid.uuid4().hex[:8]}"
            aparat_link, error = upload_to_aparat(filename, title)
            
            if aparat_link:
                send_tg_message(chat_id, f"✅ آپلود با موفقیت انجام شد!\n\n🔗 لینک استریم:\n{aparat_link}")
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
