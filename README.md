# Voice Email - Setup

## 1. Install dependencies
pip install -r requirements.txt


## 2. Create your `.env` file

cp  .env

Open `.env` and fill in:

EMAIL_USER=your_email@gmail.com

EMAIL_PASS=your_16_char_app_password

SMTP_SERVER=smtp.gmail.com

SMTP_PORT=587

IMAP_SERVER=imap.gmail.com

SECRET_KEY=change-me-to-something-random


`EMAIL_PASS` must be a Gmail **App Password**, not your normal password:
1. Turn on 2-Step Verification: https://myaccount.google.com/security
2. Create an App Password: https://myaccount.google.com/apppasswords
3. Paste the 16-character code as `EMAIL_PASS`

## 3. Run it

**Web interface:**

python app.py

Open **http://127.0.0.1:5000** in **Google Chrome** (voice recognition doesn't
work in Chromium/Brave/Firefox).

**CLI interface:**

python main.py
```
Runs in the terminal using your system microphone and speakers.

Say **"inbox"**, **"compose"**, **"read number 2"**, or **"stop"** - or in the
web version, just type into the fields and click Send/Refresh instead.
