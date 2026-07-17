import os
import requests
import uuid
import hashlib
import json
from flask import Flask, request, jsonify

app = Flask(__name__)

# ================= تنظیمات =================
TG_TOKEN = '8067819715:AAGDbuuq1Tyo7Ar8RiUsBfrRm4lyr0UnbZc'

# خواندن از Environment Variables (هرگز اینجا رمز را ننویسید)
APARAT_USERNAME = os.environ.get('APARAT_USERNAME')
APARAT_PASSWORD = os.environ.get('APARAT_PASSWORD')

if not APARAT_USERNAME or not APARAT_PASSWORD:
    print("❌ خطا: نام کاربری یا رمز عبور آپارات در Environment Variables تنظیم نشده است!")

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36',
    'Accept': 'application/json, text/plain, */*'
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

def upload_to_aparat(video_path: str, title: str, description: str = "آپلود خودکار"):
    try:
        print(f"📤 شروع فرآیند آپلود: {title}")
        
        hashed_pass = _hash_password(APARAT_PASSWORD)
        login_url = f"https://www.aparat.com/etc/api/login/luser/{APARAT_USERNAME}/lpass/{hashed_pass}"
        print(f"🔐 درخواست لاگین برای کاربر: {APARAT_USERNAME}")
        
        res_login = requests.get(login_url, headers=HEADERS, timeout=30)
        
        if res_login.status_code != 200:
            return None, f"خطای HTTP {res_login.status_code} در لاگین"
            
        data_login = res_login.json()
        if 'login' not in data_login or 'ltoken' not in data_login['login']:
            # اینجا دقیقاً همان خطایی است که شما گرفتید
            return None, f"خطای لاگین از سمت آپارات: {data_login}"
            
        ltoken = data_login['login']['ltoken']

        form_url = f"https://www.aparat.com/etc/api/uploadform/luser/{APARAT_USERNAME}/ltoken/{ltoken}"
        res_form = requests.get(form_url, headers=HEADERS, timeout=30)
        
        if res_form.status_code != 200:
            return None, f"خطای HTTP در دریافت فرم"
            
        data_form = res_form.json()
        if 'uploadform' not in data_form or 'formAction' not in data_form['uploadform']:
            return None, f"پاسخ نامعتبر از فرم: {data_form}"
            
        form_action = data_form['uploadform']['formAction']
        frm_id = data_form['uploadform']['frm-id']

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
        
        if upload_res.status_code != 200:
            return None, f"خطای HTTP {upload_res.status_code} در آپلود"
            
        try:
            data_upload = upload_res.json()
            if 'uploadpost' in data_upload and 'uid' in data_upload['uploadpost']:
                video_uid = data_upload['uploadpost']['uid']
                return f"https://www.aparat.com/v/{video_uid}", None
            else:
                return None, f"پاسخ نامعتبر: {data_upload}"
        except json.JSONDecodeError:
            return None, f"پاسخ JSON نامعتبر: {upload_res.text[:200]}"
            
    except Exception as e:
        return None, str(e)
    finally:
        if 'file_handle' in locals() and file_handle:
            file_handle.close()

# ... (بقیه کد webhook و health_check دقیقاً مثل قبل باقی می‌ماند) ...
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
            with requests.get(text, stream=True, timeout=1800) as r:
                r.raise_for_status()
                with open(filename, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        if chunk: f.write(chunk)
            
            file_size = os.path.getsize(filename)
            send_tg_message(chat_id, f"⬆️ دانلود انجام شد ({file_size / 1024 / 1024:.1f} MB). در حال آپلود...")
            
            aparat_link, error = upload_to_aparat(filename, f"ویدیو - {uuid.uuid4().hex[:8]}")
            
            if aparat_link:
                send_tg_message(chat_id, f"✅ آپلود موفق!\n\n🔗 {aparat_link}")
            else:
                send_tg_message(chat_id, f"❌ خطا در آپلود:\n{error}")
        except Exception as e:
            send_tg_message(chat_id, f"❌ خطا: {str(e)[:200]}")
        finally:
            if os.path.exists(filename): os.remove(filename)
        return jsonify({"ok": True})

    return jsonify({"ok": True})

@app.route('/', methods=['GET'])
def health_check():
    return "Bot is running!", 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
