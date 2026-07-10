"""
SMTP / IMAP Email Client
Works with Gmail (App Password), Outlook, etc.
"""
import smtplib
import imaplib
import email
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import re
import html
# html2text removed – using built-in html stripper for your package list

def strip_html(text):
    """Built-in HTML to text – no external package needed"""
    if not text:
        return ""
    # remove scripts/styles
    text = re.sub(r'<(script|style).*?</\1>', '', text, flags=re.DOTALL|re.IGNORECASE)
    # replace <br>, <p> with newlines
    text = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'</p>', '\n\n', text, flags=re.IGNORECASE)
    # strip all tags
    text = re.sub(r'<[^>]+>', '', text)
    # unescape entities
    text = html.unescape(text)
    # clean whitespace
    text = re.sub(r'\n\s*\n', '\n\n', text)
    text = re.sub(r'[ \t]+', ' ', text)
    return text.strip()

class SMTPEmailClient:
    def __init__(self, email_address, app_password, 
                 smtp_server="smtp.gmail.com", smtp_port=587,
                 imap_server="imap.gmail.com"):
        self.email_address = email_address
        self.app_password = app_password
        self.smtp_server = smtp_server
        self.smtp_port = smtp_port
        self.imap_server = imap_server

    def send_email(self, to, subject, body):
        """Send email via SMTP"""
        msg = MIMEMultipart()
        msg['From'] = self.email_address
        msg['To'] = to
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))

        try:
            server = smtplib.SMTP(self.smtp_server, self.smtp_port)
            server.starttls()
            server.login(self.email_address, self.app_password)
            server.send_message(msg)
            server.quit()
            return True, "Email sent successfully"
        except Exception as e:
            return False, str(e)

    def read_inbox(self, limit=5, unread_only=True):
        """Read inbox via IMAP"""
        try:
            mail = imaplib.IMAP4_SSL(self.imap_server)
            mail.login(self.email_address, self.app_password)
            mail.select("inbox")

            search_criteria = '(UNSEEN)' if unread_only else 'ALL'
            status, messages = mail.search(None, search_criteria)
            email_ids = messages[0].split()
            
            emails = []
            # newest first
            for eid in reversed(email_ids[-limit:]):
                status, msg_data = mail.fetch(eid, '(RFC822)')
                for response_part in msg_data:
                    if isinstance(response_part, tuple):
                        msg = email.message_from_bytes(response_part[1])
                        subject = msg.get("Subject", "No Subject")
                        sender = msg.get("From", "Unknown")
                        
                        body = ""
                        if msg.is_multipart():
                            for part in msg.walk():
                                if part.get_content_type() == "text/plain":
                                    try:
                                        body = part.get_payload(decode=True).decode(errors='ignore')
                                        break
                                    except: pass
                        else:
                            try:
                                body = msg.get_payload(decode=True).decode(errors='ignore')
                            except: 
                                body = str(msg.get_payload())

                        # strip html if needed – built-in, no html2text
                        if "<" in body and ">" in body:
                            body = strip_html(body)

                        emails.append({
                            "from": sender,
                            "subject": subject,
                            "body": body[:800],  # truncate for TTS
                            "id": eid.decode() if isinstance(eid, bytes) else str(eid)
                        })
            mail.close()
            mail.logout()
            return emails
        except Exception as e:
            print(f"IMAP error: {e}")
            return []

    def mark_read(self, email_id):
        try:
            mail = imaplib.IMAP4_SSL(self.imap_server)
            mail.login(self.email_address, self.app_password)
            mail.select("inbox")
            mail.store(email_id, '+FLAGS', '\\Seen')
            mail.close()
            mail.logout()
        except:
            pass
