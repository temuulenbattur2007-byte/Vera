"""
tools/tts.py — Text-to-Speech using Piper.
"""
import os
import threading
from pathlib import Path

VOICE_DIR  = Path(__file__).parent.parent / "voices"
VOICE_FILE = VOICE_DIR / "en_US-lessac-high.onnx"

_voice   = None
_lock    = threading.Lock()
_enabled = False


def _get_voice():
    global _voice
    if _voice is not None:
        return _voice
    if not VOICE_FILE.exists():
        print(f"[TTS] Voice file not found: {VOICE_FILE}")
        return None
    from piper import PiperVoice
    _voice = PiperVoice.load(str(VOICE_FILE))
    return _voice


def speak(text: str) -> None:
    if not _enabled:
        return
    threading.Thread(target=_speak_blocking, args=(text,), daemon=True).start()


def _speak_blocking(text: str) -> None:
    with _lock:
        try:
            voice = _get_voice()
            if not voice:
                return

            clean = _clean_for_speech(text)
            if not clean.strip():
                return

            import tempfile, subprocess, wave

            tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
            tmp_path = tmp.name
            tmp.close()

            # Use piper command line directly — most reliable method
            import shutil
            piper_exe = shutil.which("piper") or shutil.which("piper.exe")

            if piper_exe:
                # Use piper CLI
                proc = subprocess.Popen(
                    [piper_exe, "--model", str(VOICE_FILE),
                     "--output_file", tmp_path],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                proc.communicate(input=clean.encode("utf-8"))
            else:
                # Use Python API with raw audio bytes
                raw_audio = b""
                for audio_bytes in voice.synthesize_stream_raw(clean):
                    raw_audio += audio_bytes

                # Write as proper WAV
                with wave.open(tmp_path, 'wb') as wf:
                    wf.setnchannels(1)
                    wf.setsampwidth(2)
                    wf.setframerate(voice.config.sample_rate)
                    wf.writeframes(raw_audio)

            # Play
            subprocess.Popen(
                ['powershell', '-c',
                 f"(New-Object Media.SoundPlayer '{tmp_path}').PlaySync()"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            ).wait()

            try:
                os.unlink(tmp_path)
            except:
                pass

        except Exception as e:
            print(f"[TTS] Error: {e}")


def _clean_for_speech(text: str) -> str:
    import re
    text = re.sub(r'\{.*?\}', '', text, flags=re.DOTALL)
    text = re.sub(r'\*+', '', text)
    text = re.sub(r'#+\s*', '', text)
    text = re.sub(r'`+', '', text)
    text = text.replace('→', '').replace('•', '').replace('—', ',')
    text = re.sub(r'\s+', ' ', text).strip()
    return text[:300]  # Limit length for speed


def set_enabled(enabled: bool) -> None:
    global _enabled
    _enabled = enabled


def is_enabled() -> bool:
    return _enabled