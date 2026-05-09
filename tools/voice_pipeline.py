"""
tools/voice_pipeline.py — Full streaming voice pipeline.
Wake word → STT → LLM → TTS, all running locally.
"""
import threading
import queue
import numpy as np
import sounddevice as sd
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────
WAKE_WORDS      = ["hey vera", "vera", "hey vera"]
SAMPLE_RATE     = 16000
CHUNK_DURATION  = 0.5      # seconds per audio chunk
SILENCE_TIMEOUT = 1.5      # seconds of silence before processing
ENERGY_THRESHOLD = 0.01    # minimum energy to consider as speech

# ── State ─────────────────────────────────────────────────────────────────────
_running       = False
_enabled       = False
_whisper_model = None
_lock          = threading.Lock()
_audio_queue   = queue.Queue()

# Callbacks set by GUI
_on_wake       = None   # called when wake word detected
_on_transcript = None   # called with final transcript text
_on_speaking   = None   # called when Vera starts/stops speaking
_on_error      = None   # called on error


def _get_whisper():
    global _whisper_model
    if _whisper_model is not None:
        return _whisper_model
    from faster_whisper import WhisperModel
    print("[Voice] Loading Whisper model...")
    _whisper_model = WhisperModel(
        "base",
        device="cuda",
        compute_type="float16",
    )
    print("[Voice] Whisper ready.")
    return _whisper_model


def _energy(audio: np.ndarray) -> float:
    return float(np.sqrt(np.mean(audio ** 2)))


def _transcribe(audio: np.ndarray) -> str:
    model = _get_whisper()
    segments, _ = model.transcribe(
        audio,
        language="en",
        beam_size=1,
        vad_filter=True,
    )
    return " ".join(s.text for s in segments).strip()


def _contains_wake_word(text: str) -> tuple[bool, str]:
    """Check if text contains wake word. Fuzzy matching for accents/mishearing."""
    lower = text.lower().strip()

    # Exact matches — including Mongolian accent variations
    exact = ["hey vera", "vera", "hey vira", "hey veera", "hey where",
             "a vera", "hey bara", "hay vera", "heyve ra", "hey wera",
             "hey fer", "hey bera", "evera", "hey vera", "ave ra",
             "hei vera", "hey verra", "hey ver", "a ver", "hey fera",
             "hey weira", "hey veira", "hey vira", "hey vra", "hvera",
             "ei vera", "hey weraa", "hei wera", "hey wra", "he vera"]
    for wake in exact:
        if wake in lower:
            idx = lower.find(wake) + len(wake)
            remainder = text[idx:].strip(" ,.!?")
            return True, remainder

    # Fuzzy: if text starts with hey/ve/a and is short, treat as wake
    words = lower.split()
    if words and words[0] in ["hey", "ve", "vera", "vira", "veera", "bera", "wera", "hei", "hai", "he", "ei"]:
        if len(words) <= 2:
            return True, ""
        elif len(words) >= 3 and words[1] in ["vera", "vira", "wera", "bera", "where", "fera", "verra", "ver", "wra"]:
            remainder = " ".join(words[2:])
            return True, remainder

    # Fuzzy: contains "era" sound (vera mishearing)
    if "era" in lower and len(lower) < 15:
        return True, ""

    return False, text


class VoicePipeline:
    def __init__(self):
        self._thread    = None
        self._running   = False
        self._listening = False
        self._buffer    = []
        self._silence   = 0.0
        self._awake     = False

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False

    def _run(self):
        chunk_size = int(SAMPLE_RATE * CHUNK_DURATION)

        def audio_callback(indata, frames, time, status):
            if not self._running:
                return
            audio_chunk = indata[:, 0].copy()
            _audio_queue.put(audio_chunk)

        try:
            with sd.InputStream(
                samplerate=SAMPLE_RATE,
                channels=1,
                dtype="float32",
                blocksize=chunk_size,
                callback=audio_callback,
            ):
                while self._running:
                    self._process_loop()
        except Exception as e:
            if _on_error:
                _on_error(str(e))

    def _process_loop(self):
        try:
            chunk = _audio_queue.get(timeout=0.1)
        except queue.Empty:
            return

        energy = _energy(chunk)

        if not self._awake:
            # Passive listening — check for wake word
            if energy > ENERGY_THRESHOLD:
                self._buffer.append(chunk)
                if len(self._buffer) > 6:  # ~3 seconds max for wake word
                    self._buffer.pop(0)

                # Transcribe buffer to check for wake word
                audio = np.concatenate(self._buffer)
                try:
                    text = _transcribe(audio)
                    found, remainder = _contains_wake_word(text)
                    if found:
                        self._awake = True
                        self._buffer = []
                        self._silence = 0.0
                        if _on_wake:
                            _on_wake()
                        # If wake word had trailing speech, process it
                        if remainder and len(remainder) > 3:
                            self._deliver(remainder)
                            self._awake = False
                except Exception:
                    pass
            else:
                if self._buffer:
                    self._buffer.pop(0) if len(self._buffer) > 3 else None

        else:
            # Active listening — capture full command
            if energy > ENERGY_THRESHOLD:
                self._buffer.append(chunk)
                self._silence = 0.0
            else:
                self._silence += CHUNK_DURATION
                if self._buffer:
                    self._buffer.append(chunk)

                if self._silence >= SILENCE_TIMEOUT and self._buffer:
                    # Process what we heard
                    audio = np.concatenate(self._buffer)
                    self._buffer = []
                    self._silence = 0.0
                    self._awake = False

                    try:
                        text = _transcribe(audio)
                        if text and len(text) > 2:
                            self._deliver(text)
                    except Exception as e:
                        if _on_error:
                            _on_error(f"Transcribe error: {e}")

    def _deliver(self, text: str):
        if _on_transcript:
            _on_transcript(text)


# ── Singleton ─────────────────────────────────────────────────────────────────
_pipeline = VoicePipeline()


def start_pipeline(on_wake=None, on_transcript=None, on_error=None):
    global _on_wake, _on_transcript, _on_error
    _on_wake       = on_wake
    _on_transcript = on_transcript
    _on_error      = on_error
    # Pre-load whisper in background
    threading.Thread(target=_get_whisper, daemon=True).start()
    _pipeline.start()


def stop_pipeline():
    _pipeline.stop()


def is_running():
    return _pipeline._running