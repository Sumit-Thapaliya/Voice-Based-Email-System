"""
Speech-to-Text Engine
Multiple backends: Vosk (offline), Google, Whisper
Optimized for your package list:
  SpeechRecognition==3.10.1
  vosk==0.3.45
  sounddevice==0.4.7
  PyAudio==0.2.14
"""
import speech_recognition as sr
import json
import os

# Detect Vosk model
def find_vosk_model():
    candidates = [
        "model",
        "vosk-model",
        "vosk-model-small-en-us-0.15",
        "vosk-model-small-en-in-0.4",
        "vosk-model-small-hi-0.22",
        "./model",
        os.path.expanduser("~/vosk-model")
    ]
    for p in candidates:
        if os.path.isdir(p):
            return p
    return None

class STTEngine:
    def __init__(self, language="en-US", timeout=5, phrase_time_limit=7, prefer_offline=False):
        self.r = sr.Recognizer()
        self.r.pause_threshold = 1.0  # was 0.8 – longer pause = better for spelling
        self.r.phrase_threshold = 0.3
        self.r.non_speaking_duration = 0.5
        self.r.energy_threshold = 280  # was 300 – more sensitive
        self.r.dynamic_energy_threshold = True
        self.r.dynamic_energy_adjustment_damping = 0.15
        self.r.dynamic_energy_ratio = 1.5
        self.language = language  # en-US, en-IN, en-GB
        self.timeout = timeout
        self.phrase_time_limit = phrase_time_limit
        self.prefer_offline = prefer_offline

        # Vosk model detection
        self.vosk_model_path = find_vosk_model()
        if self.vosk_model_path:
            print(f"[STT] Vosk offline model found: {self.vosk_model_path}")
        else:
            print("[STT] Vosk not found – using Google online (more accurate for English)")
            print("      For offline: https://alphacephei.com/vosk/models")
            self.prefer_offline = False

        # adjust for ambient noise once
        try:
            with sr.Microphone() as source:
                print("Calibrating microphone... stay quiet 1.5s")
                self.r.adjust_for_ambient_noise(source, duration=1.5)
                print(f"  Energy threshold set to {self.r.energy_threshold}")
        except Exception as e:
            print(f"Mic calibration skipped: {e}")

    def listen(self, prompt=None, phrase_time_limit=None, timeout=None, pause_threshold=None, language=None):
        """Returns text string or None
        Accurate mode: pass phrase_time_limit=12 for email spelling
        """
        # temporary overrides for accuracy
        orig_pause = self.r.pause_threshold
        orig_phrase = self.phrase_time_limit
        orig_timeout = self.timeout
        orig_lang = self.language

        if pause_threshold is not None:
            self.r.pause_threshold = pause_threshold
        if phrase_time_limit is not None:
            ptl = phrase_time_limit
        else:
            ptl = self.phrase_time_limit
        if timeout is not None:
            to = timeout
        else:
            to = self.timeout
        lang = language or self.language

        try:
            with sr.Microphone() as source:
                # quick ambient re-adjust for accuracy
                self.r.adjust_for_ambient_noise(source, duration=0.5)
                if prompt:
                    print(f"LISTENING ({lang}, {ptl}s): {prompt}")
                try:
                    audio = self.r.listen(source, timeout=to, phrase_time_limit=ptl)
                    print("Recognizing...")
                except sr.WaitTimeoutError:
                    return None
        finally:
            # restore
            self.r.pause_threshold = orig_pause
            self.phrase_time_limit = orig_phrase
            self.timeout = orig_timeout
            self.language = orig_lang
        
        # Try backends – GOOGLE FIRST for accuracy (English)
        # 1. Google Web Speech – try multiple English dialects for accuracy
        tried_langs = [lang, "en-US", "en-IN", "en-GB", "en-AU"]
        seen = set()
        for glang in tried_langs:
            if glang in seen or not glang:
                continue
            seen.add(glang)
            try:
                text = self.r.recognize_google(audio, language=glang)
                if text.strip():
                    print(f"YOU (google {glang}): {text}")
                    return text.lower().strip()
            except sr.UnknownValueError:
                continue
            except sr.RequestError as e:
                print(f"Google STT error: {e}")
                break

        # 2. Vosk offline (if model present)
        if self.vosk_model_path:
            try:
                text = self.r.recognize_vosk(audio)
                try:
                    j = json.loads(text)
                    text = j.get("text", text)
                except:
                    pass
                if text.strip():
                    print(f"YOU (vosk): {text}")
                    return text.lower()
            except Exception:
                try:
                    from vosk import Model, KaldiRecognizer
                    model = Model(self.vosk_model_path)
                    rec = KaldiRecognizer(model, 16000)
                    wav_data = audio.get_wav_data(convert_rate=16000)
                    rec.AcceptWaveform(wav_data)
                    result = json.loads(rec.FinalResult())
                    text = result.get("text", "")
                    if text.strip():
                        print(f"YOU (vosk direct): {text}")
                        return text.lower()
                except Exception:
                    pass

        # 3. Whisper fallback
        try:
            text = self.r.recognize_whisper(audio, language="english")
            if text.strip():
                print(f"YOU (whisper): {text}")
                return text.lower()
        except Exception:
            pass

        # 4. Sphinx last resort
        try:
            text = self.r.recognize_sphinx(audio)
            if text.strip():
                print(f"YOU (sphinx): {text}")
                return text.lower()
        except Exception:
            return None
        return None

    def listen_confirm(self, prompt, max_tries=3, **kwargs):
        """Listen with confirmation loop"""
        for i in range(max_tries):
            text = self.listen(prompt if i==0 else "Please repeat", **kwargs)
            if text:
                return text
        return None

    def listen_yes_no(self, prompt="Say yes or no", max_tries=5, timeout=6):
        """High-accuracy yes/no listener – v3 – Nepal accent tuned
        Solves 'yes gets cancelled' bug
        """
        # Expanded for South Asian English accent mis-recognitions
        YES_WORDS = [
            "yes","yeah","yep","yup","sure","correct","right","yea",
            "ya","yas","yash","yess","yes sir","yeah sir",
            "send","confirm","ok","okay","please","do it","go","go ahead",
            "affirmative","true","1","one","first","s","y",
            # common STT mis-hears for "yes" with Nepali accent:
            "jes","jess","yesh","esh","ace","s","s.","test","yet","yesterday",
            "ye","he","hey","hey sir","yessir","is","this","this is"
        ]
        NO_WORDS = [
            "no","nope","nah","cancel","stop","don't","dont","wrong",
            "not","never","negative","noo","n","2","two","second",
            "quit","abort","back","no sir","no no"
        ]
        # save original recognizer settings
        orig_energy = self.r.energy_threshold
        orig_pause = self.r.pause_threshold
        orig_dynamic = self.r.dynamic_energy_threshold
        
        # make mic MORE sensitive for short "yes"
        # lower threshold by 30%, disable dynamic so it doesn't creep up
        try:
            self.r.energy_threshold = max(150, int(orig_energy * 0.7))
            self.r.dynamic_energy_threshold = False
            self.r.pause_threshold = 0.6  # short word, quick stop

            for attempt in range(max_tries):
                # alternate language each try: en-IN better for Nepal, en-US fallback
                use_lang = "en-IN" if attempt % 2 == 0 else "en-US"
                spoken_prompt = prompt if attempt == 0 else f"Attempt {attempt+1} of {max_tries}. Say YES loudly, or NO to cancel. You can also say SEND, OK, or ONE for yes. TWO for no."
                
                print(f"\n[YES/NO listening – try {attempt+1}/{max_tries} – mic threshold {self.r.energy_threshold} – lang {use_lang}]")
                text = self.listen(
                    spoken_prompt,
                    phrase_time_limit=4,
                    timeout=timeout,
                    pause_threshold=0.6,
                    language=use_lang
                )
                if not text:
                    print(f"  [yes/no] No speech detected (try {attempt+1}). Speak LOUDER, closer to mic.")
                    # lower threshold even more each fail
                    self.r.energy_threshold = max(120, self.r.energy_threshold - 30)
                    continue

                txt = text.lower().strip()
                print(f"  [yes/no debug] heard: '{txt}' (lang {use_lang})")

                # 1. exact match
                if txt in YES_WORDS:
                    print("  → YES (exact)")
                    return True
                if txt in NO_WORDS:
                    print("  → NO (exact)")
                    return False
                # 2. contains
                # check NO first – to avoid "yesterday" false yes
                if any(n == txt or f" {n} " in f" {txt} " or txt.startswith(n+" ") or txt.endswith(" "+n) for n in NO_WORDS):
                    print("  → NO (contains)")
                    return False
                if any(y == txt or f" {y} " in f" {txt} " or txt.startswith(y+" ") or txt.endswith(" "+y) for y in YES_WORDS):
                    print("  → YES (contains)")
                    return True
                # substring fallback (more permissive)
                if any(n in txt for n in [" nope", "cancel", "stop", " no ", " not ", "never"]):
                    print("  → NO (substring)")
                    return False
                if any(y in txt for y in [" yes", "yeah", "yep", "sure", "correct", "ok", "send", "confirm", "go ahead"]):
                    print("  → YES (substring)")
                    return True
                # 3. fuzzy first-letter with length check – very permissive for short answers
                # common mis-recognitions from Google STT Nepal accent:
                # "yes" → "s", "jes", "yash", "esh", "ace", "test", "yet"
                first = txt[:3].lower() if txt else ""
                if txt in ["s","y","ya","ye","es","is","ok","1","go","do","so","she","he","hey","hi","a","i","ace","test","yet","jet","jess","j","c","see","sea","say","same","send","sure","sir"]:
                    print(f"  → YES (fuzzy short '{txt}')")
                    return True
                if txt.startswith("n") or "no" in txt or "cancel" in txt or "stop" in txt:
                    print(f"  → NO (fuzzy)")
                    return False
                # 4. length heuristic – very short 1-3 char unknown = probably yes (user is trying)
                # better to confirm than cancel – user complaint is auto-cancel
                if len(txt) <= 3 and attempt >= 2:
                    print(f"  → YES (short fallback, attempt {attempt+1}) – assuming affirmative to prevent auto-cancel")
                    return True

                print(f"  → Unclear: '{txt}' – retrying…")
            # all tries exhausted
            print("  [yes/no] All tries exhausted – returning None (will ask caller to retry)")
            return None
        finally:
            # restore
            self.r.energy_threshold = orig_energy
            self.r.pause_threshold = orig_pause
            self.r.dynamic_energy_threshold = orig_dynamic

    def listen_email(self, prompt="Spell email address"):
        """Accurate email dictation – longer listen, slower pause – ENGLISH"""
        # temporarily lower energy threshold – spelling is often quieter
        orig_energy = self.r.energy_threshold
        try:
            self.r.energy_threshold = max(180, int(orig_energy * 0.8))
            for attempt in range(3):
                text = self.listen(
                    prompt if attempt==0 else "Please spell email again, slowly. Say: name … AT … gmail … DOT … com",
                    phrase_time_limit=14,
                    timeout=8,
                    pause_threshold=1.5,
                    language="en-IN"  # en-IN FAR better for Nepal accent than en-US
                )
                if text:
                    print(f"  [email debug] raw: '{text}'")
                    return text
                print("  [email] no speech detected, lowering mic threshold…")
                self.r.energy_threshold = max(150, self.r.energy_threshold - 40)
            return None
        finally:
            self.r.energy_threshold = orig_energy

    def listen_long(self, prompt="Speak now", seconds=15):
        """Long dictation for email body – English"""
        return self.listen(prompt, phrase_time_limit=seconds, timeout=8, pause_threshold=1.2, language=self.language)
