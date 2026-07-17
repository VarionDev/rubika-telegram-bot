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

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'fa-IR,fa;q=0.9',
    'Connection': 'keep-alive'
}
# ============================================

def send_tg_message(chat_id, text):
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    try:
        requests.post(url, json={"chat_id": chat_id, "text": text}, timeout=10)
    except Exception as e:
        print(f"خطا در ارسال پیام: {e}")

def _hash_password(password: str) -> str:
    md5_hash = hashlib.md5(password.encode('utf-8')).hexdigest()
    sha1_hash = hashlib.sha1(md5_hash.encode('utf-8')).hexdigest()
    return sha1_hash

def upload_to_aparat(video_path: str, title: str, description: str = "آپلود خودکار"):
    try:
        print(f"📤 شروع فرآیند آپلود: {title}")
        
        # بررسی حیاتی متغیرهای محیطی
        if not APARAT_USERNAME or not APARAT_PASSWORD or APARAT_USERNAME == 'your_aparat_username':
            print("❌ خطای بحرانی: متغیرهای محیطی آپارات تنظیم نشده‌اند!")
            return None, "خطای پیکربندی: نام کاربری یا رمز عبور در سرور تنظیم نشده است."

        # ۱. لاگین
        hashed_pass = _hash_password(APARAT_PASSWORD)
        login_url = f"https://www.aparat.com/etc/api/login/luser/{APARAT_USERNAME}/lpass/{hashed_pass}"
        print(f"🔐 درخواست لاگین. کاربر: {APARAT_USERNAME}")
        
        res_login = requests.get(login_url, headers=HEADERS, timeout=30)
        print(f"📥 لاگین -> Status: {res_login.status_code} | Headers: {dict(res_login.headers)}")
        print(f"📥 لاگین -> Raw Text: '{res_login.text.strip()}'")
        
        if res_login.status_code != 200:
            return None, f"خطای HTTP {res_login.status_code} در لاگین."
            
        try:
            data_login = res_login.json()
        except json.JSONDecodeError:
            return None, f"پاسخ غیر JSON در لاگین. متن سرور: '{res_login.text[:200]}'"
            
        if 'login' not in data_login or 'ltoken' not in data_login['login']:
            return None, f"پاسخ نامعتبر از لاگین: {data_login}"
            
        ltoken = data_login['login']['ltoken']

        # ۲. دریافت فرم
        form_url = f"https://www.aparat.com/etc/api/uploadform/luser/{APARAT_USERNAME}/ltoken/{ltoken}"
        res_form = requests.get(form_url, headers=HEADERS, timeout=30)
        
        try:
            data_form = res_form.json()
            form_action = data_form['uploadform']['formAction']
            frm_id = data_form['uploadform']['frm-id']
        except Exception as e:
            return None, f"خطا در دریافت فرم: {str(e)} | پاسخ: {res_form.text[:200]}"

        # ۳. آپلود
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
        
        try:
            data_upload = upload_res.json()
            if 'uploadpost' in data_upload and 'uid' in data_upload['uploadpost']:
                return f"https://www.aparat.com/v/{data_upload['uploadpost']['uid']}", None
            else:
                return None, f"پاسخ نامعتبر آپلود: {data_upload}"
        except json.JSONDecodeError:
            return None, f"پاسخ غیر JSON در آپلود. Status: {upload_res.status_code} | Text: {upload_res.text[:300]}"
            
    except Exception as e:
        return None, f"خطای استثناء: {str(e)}"
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
        send_tg_message(chat_id, "⏳ در حال بررسی و دانلود لینک...")
        
        filename = f"/tmp/video_{uuid.uuid4().hex}.mp4"
        try:
            print(f"⬇️ شروع دانلود از: {text}")
            with requests.get(text, stream=True, timeout=120, allow_redirects=True) as r:
                print(f"📥 وضعیت دانلود: {r.status_code}")
                print(f"📥 هدرهای دانلود: {dict(r.headers)}")
                r.raise_for_status()
                
                with open(filename, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
            
            file_size = os.path.getsize(filename)
            print(f"✅ حجم فایل ذخیره شده روی دیسک: {file_size} بایت ({file_size / 1024 / 1024:.2f} MB)")
            
            if file_size == 0:
                send_tg_message(chat_id, "❌ خطا: فایل دانلود شده کاملاً خالی (0 بایت) است.\n\n💡 دلیل: این لینک منقضی شده، یا سرور مبدأ دانلود توسط ربات‌ها را مسدود کرده است. لطفاً یک لینک دیگر تست کنید.")
                return jsonify({"ok": True})
            
            send_tg_message(chat_id, f"⬆️ دانلود موفق ({file_size / 1024 / 1024:.1f} MB). در حال آپلود در آپارات...")
            
            aparat_link, error = upload_to_aparat(filename, f"ویدیو - {uuid.uuid4().hex[:8]}")
            
            if aparat_link:
                send_tg_message(chat_id, f"✅ آپلود موفق!\n\n🔗 {aparat_link}")
            else:
                send_tg_message(chat_id, f"❌ خطا در آپلود:\n{error}")
                
        except requests.exceptions.HTTPError as e:
            send_tg_message(chat_id, f"❌ خطای شبکه در دانلود: سرور مبدأ دسترسی را رد کرد (HTTP {e.response.status_code}).")
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
