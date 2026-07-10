"""
Text-to-Speech Engine
Supports offline pyttsx3 and online gTTS
"""
import pyttsx3
import os
import tempfile
# gTTS and playsound are optional - lazy loaded only if engine_type=="online"
try:
    from gtts import gTTS
    HAS_GTTS = True
except:
    HAS_GTTS = False

try:
    from playsound import playsound
    HAS_PLAYSOUND = True
except:
    HAS_PLAYSOUND = False

class TTSEngine:
    def __init__(self, engine_type="offline", lang="en", rate=170, voice_gender="female"):
        """
        engine_type: "offline" (pyttsx3) or "online" (gTTS)
        lang: 'en', 'ne', 'hi', etc.
        """
        # auto-fallback if gTTS not installed
        if engine_type == "online" and not HAS_GTTS:
            engine_type = "offline"
        self.engine_type = engine_type
        self.lang = lang
        
        # always init offline engine as fallback
        self.engine = pyttsx3.init()
        self.engine.setProperty('rate', rate)
        voices = self.engine.getProperty('voices')
        # try to pick gender
        if voices:
            if voice_gender == "female" and len(voices) > 1:
                self.engine.setProperty('voice', voices[1].id)
            else:
                self.engine.setProperty('voice', voices[0].id)
    
    def speak(self, text):
        print(f"ASSISTANT: {text}")
        if self.engine_type == "offline" or not HAS_GTTS:
            self.engine.say(text)
            self.engine.runAndWait()
        else:
            # gTTS online
            try:
                tts = gTTS(text=text, lang=self.lang, slow=False)
                with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as fp:
                    temp_path = fp.name
                tts.save(temp_path)
                if HAS_PLAYSOUND:
                    playsound(temp_path)
                else:
                    os.system(f"mpg123 {temp_path} > /dev/null 2>&1 || afplay {temp_path} > /dev/null 2>&1")
                os.remove(temp_path)
            except Exception as e:
                print(f"TTS online failed, fallback: {e}")
