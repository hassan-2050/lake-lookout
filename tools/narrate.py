"""Text to speech for the demo narration, with an open-weight model run locally.

Kokoro-82M (Apache-2.0) through kokoro-onnx: no cloud, no key, the same
"open model on your own machine" idea as the app itself. The model files are
downloaded once into ~/.cache/lake-lookout/kokoro (about 340 MB, not in git):

    https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx
    https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin

Each line can be checked by transcribing it back with Gemma 4 (see check()),
which is how the narration was verified without listening to it.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import soundfile as sf

MODEL_DIR = Path.home() / ".cache" / "lake-lookout" / "kokoro"
VOICE = "af_heart"
SPEED = 1.0


@lru_cache(maxsize=1)
def _engine():
    from kokoro_onnx import Kokoro
    onnx, voices = MODEL_DIR / "kokoro-v1.0.onnx", MODEL_DIR / "voices-v1.0.bin"
    if not (onnx.exists() and voices.exists()):
        raise SystemExit(f"Kokoro model files not found in {MODEL_DIR}; see tools/narrate.py")
    return Kokoro(str(onnx), str(voices))


def say(text: str, dest: Path, voice: str = VOICE) -> float:
    """Write `text` as speech to `dest` (WAV). Returns its length in seconds."""
    samples, rate = _engine().create(text, voice=voice, speed=SPEED,
                                     lang="en-us" if voice.startswith("a") else "en-gb")
    sf.write(dest, samples, rate)
    return len(samples) / rate


def check(path: Path) -> str:
    """What Gemma 4 hears in the clip: a round-trip test of intelligibility."""
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from lookout import audio, gemma
    return gemma.transcribe(audio.chunks_b64(path))["text"]
