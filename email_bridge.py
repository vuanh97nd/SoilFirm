"""
SoilFirm Pro Email Bridge
- Email máy chủ (gửi thông báo/quét IMAP): vuanh97nd@gmail.com
- Email Admin (nhận thông báo/gửi phản hồi): vuanh97nd1@gmail.com
- Chu kỳ quét: 30 giây (mặc định)
"""
import email
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import parseaddr
import hashlib
import imaplib
import json
import logging
import re
import secrets
import smtplib
import sqlite3
import ssl
import time
import requests

# ============================================================
# CẤU HÌNH HỆ THỐNG
# ============================================================
ADMIN_EMAIL = 'vuanh97nd1@gmail.com'           # Hộp thư Admin nhận thông báo và gửi phản hồi
MAIL_USER = 'vuanh97nd@gmail.com'.strip()      # Tài khoản máy chủ dùng để gửi SMTP và quét IMAP
MAIL_PASSWORD = 'wgky txeu dnkt slbk'.replace(' ', '').strip()  # Mật khẩu ứng dụng Gmail 16 ký tự

BASE = 'https://soilfirm-api.vuanh97nd.workers.dev'
ADMIN_USER = 'admin'
ADMIN_KEY = 'P2ss@2026'

IMAP_FOLDER = 'INBOX'
POLL_INTERVAL = 30  # Chu kỳ quét mặc định 30 giây
# ============================================================

connection = sqlite3.connect('support_mail.sqlite3')
connection.executescript('''
CREATE TABLE IF NOT EXISTS notified (
    fingerprint TEXT PRIMARY KEY, 
    token TEXT UNIQUE, 
    peer TEXT NOT NULL, 
    sent INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS replies (message_id TEXT PRIMARY KEY);
CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
''')
connection.execute('INSERT OR IGNORE INTO metadata VALUES(?,?)', ('started_at', datetime.now(timezone.utc).isoformat()))
connection.commit()
session = requests.Session()

def test_connection():
    """Kiểm tra xác thực Google ngay khi khởi động"""
    print(f"[*] Đang kiểm tra kết nối tài khoản máy chủ: {MAIL_USER} ...")
    try:
        with imaplib.IMAP4_SSL('imap.gmail.com') as mb:
            mb.login(MAIL_USER, MAIL_PASSWORD)
            mb.select(IMAP_FOLDER)
        print("[+] Kết nối IMAP (Nhận mail phản hồi) THÀNH CÔNG!")
        
        with smtplib.SMTP_SSL('smtp.gmail.com', 465, context=ssl.create_default_context()) as smtp:
            smtp.login(MAIL_USER, MAIL_PASSWORD)
        print(f"[+] Kết nối SMTP (Gửi thông báo tới {ADMIN_EMAIL}) THÀNH CÔNG!")
        return True
    except Exception as e:
        print(f"[-] LỖI XÁC THỰC GOOGLE: {e}")
        return False

def api(route, peer='', **payload):
    response = session.post(BASE + route, json={'username': ADMIN_USER, 'key': ADMIN_KEY, 'peer': peer, **payload}, timeout=30)
    response.raise_for_status()
    data = response.json()
    if not data.get('success'):
        raise RuntimeError(data.get('message', 'API rejected request'))
    return data

def acknowledge(message_id):
    response = session.post(BASE + '/api/admin/email/ack', headers={'admin-key': ADMIN_KEY}, json={'message_id': message_id}, timeout=20)
    response.raise_for_status()
    if not response.json().get('success'):
        raise RuntimeError('Email acknowledgment failed')

def notify_offline():
    response = session.get(BASE + '/api/admin/email/pending', headers={'admin-key': ADMIN_KEY}, timeout=20)
    response.raise_for_status()
    for message in response.json().get('messages', []):
        peer = message['sender']
        fingerprint = hashlib.sha256(json.dumps([peer, message['id'], message.get('sent_at'), message.get('text')], ensure_ascii=False).encode()).hexdigest()
        row = connection.execute('SELECT token, sent FROM notified WHERE fingerprint=?', (fingerprint,)).fetchone()
        if row and row[1]:
            acknowledge(message['id'])
            continue
        token = row[0] if row else secrets.token_urlsafe(18)
        if not row:
            connection.execute('INSERT INTO notified(fingerprint, token, peer) VALUES(?,?,?)', (fingerprint, token, peer))
            connection.commit()
        
        msg = EmailMessage()
        msg['From'] = MAIL_USER
        msg['To'] = ADMIN_EMAIL
        msg['Reply-To'] = MAIL_USER
        msg['Subject'] = f'SoilFirm Pro support [{token}] · {peer}'
        msg['Message-ID'] = f'<{fingerprint}@soilfirm.support>'
        msg['X-SoilFirm-Notification'] = '1'
        msg.set_content(
            f'User: {peer}\n'
            f'Time: {message.get("sent_at", "")}\n\n'
            f'{message.get("text", "")}\n\n'
            f'Reply above the quoted message to send your response to the user in SoilFirm Pro.'
        )
        
        if message.get('image'):
            import base64
            data = api('/api/chat/image', peer, message_id=message['id'])['image']['data']
            msg.add_attachment(base64.b64decode(data), maintype='image', subtype='jpeg', filename='support.jpg')
        
        with smtplib.SMTP_SSL('smtp.gmail.com', 465, context=ssl.create_default_context()) as smtp:
            smtp.login(MAIL_USER, MAIL_PASSWORD)
            smtp.send_message(msg)
            
        connection.execute('UPDATE notified SET sent=1 WHERE fingerprint=?', (fingerprint,))
        connection.commit()
        acknowledge(message['id'])
        logging.info(f"Đã chuyển tiếp tin nhắn từ '{peer}' đến {ADMIN_EMAIL}")

def reply_text(msg):
    part = msg.get_body(preferencelist=('plain',))
    if not part:
        return ''
    text = part.get_content()
    lines = []
    for line in text.splitlines():
        if line.startswith('>') or re.match(r'^(On .+wrote:|Vào .+đã viết:|User: |Time: |Reply above|-----Original)', line):
            break
        lines.append(line)
    return '\n'.join(lines).strip()[:2000]

def receive_replies():
    with imaplib.IMAP4_SSL('imap.gmail.com') as mailbox:
        mailbox.login(MAIL_USER, MAIL_PASSWORD)
        mailbox.select(IMAP_FOLDER)
        _, result = mailbox.uid('search', None, 'UNSEEN')
        for uid in result[0].split():
            status, parts = mailbox.uid('fetch', uid, '(BODY.PEEK[])')
            if status != 'OK':
                continue
            raw = next((p[1] for p in parts if isinstance(p, tuple)), None)
            if raw is None:
                continue
            from email import policy
            msg = email.message_from_bytes(raw, policy=policy.default)
            
            if parseaddr(msg.get('From', ''))[1].casefold() != ADMIN_EMAIL.casefold():
                continue
            
            authentication = ' '.join(msg.get_all('Authentication-Results', []))
            if not re.search(r'dkim=pass[^;]*(?:header\.i=@gmail\.com|header\.d=gmail\.com)', authentication, re.I):
                continue
                
            subject = str(msg.get('Subject', ''))
            match = re.search(r'\[([A-Za-z0-9_-]{20,40})\]', subject)
            if not match or msg.get('X-SoilFirm-Notification'):
                continue
                
            row = connection.execute('SELECT peer FROM notified WHERE token=? AND sent=1', (match.group(1),)).fetchone()
            if not row:
                continue
                
            message_id = hashlib.sha256(raw).hexdigest()
            if connection.execute('SELECT 1 FROM replies WHERE message_id=?', (message_id,)).fetchone():
                continue
                
            payload = {'text': reply_text(msg), 'client_id': 'email_' + message_id}
            for part in msg.iter_attachments():
                if part.get_content_type().startswith('image/'):
                    from io import BytesIO
                    from PIL import Image, ImageOps
                    import base64
                    image = ImageOps.exif_transpose(Image.open(BytesIO(part.get_payload(decode=True)))).convert('RGB')
                    image.thumbnail((1600, 1600))
                    out = BytesIO()
                    image.save(out, 'JPEG', quality=85)
                    image.thumbnail((300, 220))
                    thumb = BytesIO()
                    image.save(thumb, 'JPEG', quality=75)
                    if len(out.getvalue()) <= 2 * 1024 * 1024:
                        payload['image'] = {
                            'mime': 'image/jpeg',
                            'name': 'reply.jpg',
                            'data': base64.b64encode(out.getvalue()).decode(),
                            'thumbnail': base64.b64encode(thumb.getvalue()).decode()
                        }
                    break
                    
            if not payload['text'] and 'image' not in payload:
                continue
                
            api('/api/chat/send', row[0], **payload)
            connection.execute('INSERT OR IGNORE INTO replies VALUES(?)', (message_id,))
            connection.commit()
            mailbox.uid('store', uid, '+FLAGS', r'(\Seen)')
            logging.info(f"Đã chuyển tiếp phản hồi từ Gmail vào phòng chat với '{row[0]}'")

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    
    if not test_connection():
        input("\nNhấn phím Enter để đóng...")
        exit(1)
        
    logging.info(f"SoilFirm Pro Email Bridge đang hoạt động (quét mỗi {POLL_INTERVAL} giây)...")
    while True:
        for operation in (notify_offline, receive_replies):
            try:
                operation()
            except Exception as exc:
                logging.error('%s thất bại: %s', operation.__name__, str(exc))
        time.sleep(POLL_INTERVAL)