"""
Shared voice/text email-parsing logic.
Used by BOTH main.py (CLI) and app.py (web) so the two interfaces
always behave identically.
"""
import re

try:
    from email_validator import validate_email, EmailNotValidError
    HAS_EMAIL_VALIDATOR = True
except Exception:
    HAS_EMAIL_VALIDATOR = False

# --- CONTACTS: voice shortcuts ---
CONTACTS = {
    "test": "test@example.com",
    "john": "john.doe@gmail.com",
    "xyz": "xyz@gmail.com",
    # add your own
}

# --- ACCURATE YES/NO ---
YES_WORDS = ["yes", "yeah", "yep", "yup", "sure", "correct", "right", "yea", "ya", "yas",
             "yess", "send", "confirm", "ok", "okay", "please", "do it", "go", "go ahead",
             "affirmative", "true", "s", "y", "1", "one", "proceed", "continue"]
NO_WORDS = ["no", "nope", "nah", "cancel", "stop", "don't", "dont", "wrong", "not", "never",
            "negative", "noo", "n", "2", "two", "quit", "abort", "back"]


def is_yes(text):
    if not text:
        return None
    t = text.lower().strip()
    if t in YES_WORDS:
        return True
    if t in NO_WORDS:
        return False
    if any(y in t for y in YES_WORDS) and not any(n in t for n in NO_WORDS):
        return True
    if any(n in t for n in NO_WORDS):
        return False
    if t.startswith("y") or t.startswith("s"):
        return True
    if t.startswith("n") or t.startswith("c"):
        return False
    return None


def clean_email_spoken(text):
    """Accurate spoken email parser – English only
    Handles: 'john at gmail dot com', 'r a m at the rate gmail dot com', etc.
    """
    if not text:
        return None
    text = text.lower().strip()
    replacements = [
        (" at the rate ", "@"), (" attherate ", "@"), (" at rate ", "@"),
        (" at therate ", "@"), (" at the red ", "@"), (" at red ", "@"),
        (" at ", "@"), (" at", "@"), (" et ", "@"),
        (" at gmail", "@gmail"), (" ad ", "@"),
        (" dot com", ".com"), (" dotcom", ".com"), (" dot com ", ".com"),
        (" dot ", "."), (" . ", "."),
        (" underscore ", "_"), (" under score ", "_"), (" underscored ", "_"),
        (" dash ", "-"), (" hyphen ", "-"), (" minus ", "-"),
        (" gmail com", "gmail.com"),
        (" yahoo com", "yahoo.com"),
        (" hotmail com", "hotmail.com"),
        (" outlook com", "outlook.com"),
        ("  ", " "),
    ]
    t = f" {text} "
    for a, b in replacements:
        t = t.replace(a, b)
    t = t.replace(" ", "")
    t = t.replace("@@", "@").replace("..", ".").replace("_.", ".").replace("._", ".")
    t = re.sub(r'[^a-z0-9@._+-]', '', t)
    if "@gmailcom" in t:
        t = t.replace("@gmailcom", "@gmail.com")
    if "@yahoocom" in t:
        t = t.replace("@yahoocom", "@yahoo.com")
    if t.endswith("@gmail"):
        t += ".com"
    if t.endswith("@yahoo"):
        t += ".com"
    if "@" not in t or "." not in t.split("@")[-1]:
        return None
    try:
        local, domain = t.split("@", 1)
        if len(local) < 1 or len(domain) < 3 or "." not in domain:
            return None
    except Exception:
        return None
    if HAS_EMAIL_VALIDATOR:
        try:
            v = validate_email(t, check_deliverability=False)
            return v.normalized
        except EmailNotValidError:
            return None
    return t


def resolve_contact(spoken):
    """Returns (email, is_confident:bool)"""
    if not spoken:
        return None, False
    spoken_l = spoken.lower().strip()
    for name, email in CONTACTS.items():
        if name == spoken_l or name in spoken_l.split():
            return email, True
    parsed = clean_email_spoken(spoken)
    if parsed:
        return parsed, True
    guess = re.sub(r'[^a-z0-9]', '', spoken_l) + "@gmail.com"
    return guess, False


def spell_out(email):
    """Return the character-by-character spelled version of an email,
    e.g. 'j o h n at g m a i l dot c o m' — used to read/display it back
    for confirmation before sending."""
    return " ".join(list(email.replace("@", " at ").replace(".", " dot ")))
