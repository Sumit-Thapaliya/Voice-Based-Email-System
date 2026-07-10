"""
Voice-Based Email System - Python
by Arena Agent
Run: python main.py
"""
from tts_engine import TTSEngine
from stt_engine import STTEngine
from email_client_smtp import SMTPEmailClient as EmailClient

# Shared parsing/contact logic - also used by app.py (web interface)
from email_logic import CONTACTS, is_yes, clean_email_spoken, resolve_contact, spell_out


def spell_out_email(email, tts):
    """Read email character by character for confirmation – prevents mis-send"""
    tts.speak(f"Email is: {spell_out(email)}")

def main():
    # ENGLISH ONLY BUILD
    # STT: en-US = American English, en-IN = Indian English (better for Nepal accent)
    # TTS: lang="en", offline pyttsx3 = system English voice
    tts = TTSEngine(engine_type="offline", lang="en", rate=160, voice_gender="female")
    stt = STTEngine(language="en-US", prefer_offline=False)  # English only
    # For Nepal accent recognition (recommended): use "en-IN" instead of "en-US"
    # stt = STTEngine(language="en-IN", prefer_offline=False)

    tts.speak("Welcome to Voice Email System. English mode activated. Initializing email client.")

    # --- CONFIGURE YOUR EMAIL HERE ---
    # EMAIL/APP_PASSWORD come only from .env - nothing is hardcoded in this file.
    from dotenv import load_dotenv
    import os
    load_dotenv()
    EMAIL = os.getenv("EMAIL_USER", "")
    APP_PASSWORD = os.getenv("EMAIL_PASS", "")

    if not EMAIL or not APP_PASSWORD:
        tts.speak("Please configure your email in a .env file first.")
        print("\n*** Create a .env file with EMAIL_USER and EMAIL_PASS set ***\n")
        return

    email_client = EmailClient(EMAIL, APP_PASSWORD)

    tts.speak("System ready. Say inbox, compose, read, or exit.")

    while True:
        tts.speak("What would you like to do?")
        command = stt.listen("Waiting for command...")
        if not command:
            tts.speak("I did not hear you. Please repeat.")
            continue

        # INBOX
        if any(k in command for k in ["inbox", "read", "check mail", "unread", "show"]):
            tts.speak("Checking your inbox")
            emails = email_client.read_inbox(limit=5, unread_only=True)
            if not emails:
                tts.speak("You have no unread emails.")
                continue
            tts.speak(f"You have {len(emails)} unread emails.")
            for i, mail in enumerate(emails, 1):
                tts.speak(f"Email {i}, from {mail['from'].split('<')[0]}. Subject: {mail['subject']}")
                tts.speak("Say read, next, repeat, or stop.")
                action = stt.listen()
                if action and "read" in action:
                    tts.speak(mail['body'][:500])
                elif action and "stop" in action:
                    break
                # else continue to next

        # COMPOSE – ACCURATE VERSION
        elif any(k in command for k in ["compose", "send", "write", "new mail", "email", "mail"]):
            # --- STEP 1: RECIPIENT – 3 tries, email mode ---
            to_email = None
            for attempt in range(3):
                if attempt == 0:
                    tts.speak("Who do you want to send to? Say a contact name like mom, john, or test. Or spell the full email address slowly. Say at, then dot com.")
                else:
                    tts.speak("Let's try the email again. Speak slowly. For example: ram at gmail dot com")
                
                # use long listen for email spelling – 12 seconds, high pause
                to_spoken = stt.listen_email("Listening for email…") if hasattr(stt, 'listen_email') else stt.listen("Recipient?", phrase_time_limit=12, pause_threshold=1.4, language="en-IN")
                
                if not to_spoken:
                    tts.speak("I didn't catch that.")
                    continue

                print(f"[DEBUG] heard recipient raw: '{to_spoken}'")
                email, confident = resolve_contact(to_spoken)
                if not email:
                    tts.speak("That didn't sound like a valid email. Try again.")
                    continue

                # spell it back character by character
                tts.speak("I heard:")
                spell_out_email(email, tts)
                tts.speak("Is this correct? Say YES or NO. Loud and clear.")

                # use accurate yes/no listener
                if hasattr(stt, 'listen_yes_no'):
                    yn = stt.listen_yes_no("Yes or No?")
                else:
                    resp = stt.listen("Yes or No?", phrase_time_limit=3, pause_threshold=0.7)
                    yn = is_yes(resp)
                
                print(f"[DEBUG] yes/no = {yn} from '{resp if 'resp' in locals() else 'via listen_yes_no'}'")

                if yn is True:
                    to_email = email
                    tts.speak(f"Recipient confirmed: {email.split('@')[0]}")
                    break
                elif yn is False:
                    tts.speak("Okay, cancelled that address. Let's try again.")
                    continue
                else:
                    # unclear – read back again and ask
                    tts.speak(f"I'm not sure. I heard {email}. Is that right? Say yes or no.")
                    continue

            if not to_email:
                tts.speak("Could not get a valid email after 3 tries. Cancelling compose.")
                continue

            # --- STEP 2: SUBJECT ---
            tts.speak("What is the subject?")
            subject = stt.listen_confirm("Subject?", max_tries=2) or "Voice email, no subject"
            tts.speak(f"Subject is: {subject}")

            # --- STEP 3: BODY – long dictation ---
            tts.speak("Speak your message now. You have 15 seconds.")
            if hasattr(stt, 'listen_long'):
                body = stt.listen_long("Message…", seconds=15)
            else:
                body = stt.listen("Message", phrase_time_limit=15, pause_threshold=1.2)
            body = body or ""
            if body:
                tts.speak(f"You said: {body}")
            else:
                tts.speak("No message heard. Sending blank body, okay?")
                body = "(sent by voice email)"

            # --- STEP 4: FINAL SEND CONFIRM – 3 tries, accurate yes/no ---
            tts.speak(f"Ready to send to {to_email.split('@')[0]}. Subject {subject}.")
            tts.speak("Say YES to send now. Say NO to cancel.")
            send_ok = None
            for i in range(3):
                if hasattr(stt, 'listen_yes_no'):
                    send_ok = stt.listen_yes_no("YES to send, NO to cancel" if i>0 else None, max_tries=1)
                else:
                    r = stt.listen("Yes or No?", phrase_time_limit=3, pause_threshold=0.7, language="en-US")
                    send_ok = is_yes(r)
                    print(f"[SEND DEBUG] heard '{r}' -> {send_ok}")
                if send_ok is True:
                    break
                if send_ok is False:
                    break
                # unclear – ask again
                tts.speak("I didn't catch yes or no. Please say YES clearly to send, NO to cancel.")

            if send_ok is True:
                tts.speak("Sending email now.")
                ok, msg = email_client.send_email(to_email, subject, body)
                if ok:
                    tts.speak("Email sent successfully.")
                else:
                    tts.speak(f"Failed to send. {msg}")
            else:
                tts.speak("Email cancelled. Not sent.")

        elif any(k in command for k in ["exit", "quit", "close", "stop", "goodbye"]):
            tts.speak("Goodbye. Closing voice email.")
            break

        else:
            tts.speak("Command not recognized. Say inbox, compose, or exit.")

if __name__ == "__main__":
    main()