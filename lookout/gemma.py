"""Talk to a local Gemma model through Ollama's native chat API.

Photos and audio both travel in the message's `images` list as base64. Ollama
routes each by its content, and Gemma 4's E2B and E4B models accept both.

Native /api/chat rather than the OpenAI-compatible route, for three reasons:
it takes `format` as a JSON schema, so the checklist comes back in the right
shape or not at all; it takes `num_ctx`, because Ollama's default context can
silently cut the front off a long prompt; and it reports load, prompt and
generation timings separately, which is how the latency figures in the README
were measured.

A truncated or empty answer raises an error. A cut-off answer is a wrong answer
that looks like a right one.
"""
from __future__ import annotations

import base64
import io
import json
import os
import urllib.error
import urllib.request

from PIL import Image, ImageOps

DEFAULT_MODEL = "gemma4:e4b"
BASE_URL = os.environ.get("LOOKOUT_OLLAMA", "http://127.0.0.1:11434")
SEED = 20261010
MAX_IMAGE_SIDE = 1024


class ModelError(RuntimeError):
    pass


def image_b64(path, max_side: int = MAX_IMAGE_SIDE) -> str:
    """A photo as base64 JPEG, upright and no larger than `max_side`.

    Phones store most photos sideways with a rotation flag; the model is shown
    the photo the way the hiker saw it. Shrinking is also what keeps a 12 MP
    photo from dominating the prompt.
    """
    with Image.open(path) as im:
        im = ImageOps.exif_transpose(im).convert("RGB")
        im.thumbnail((max_side, max_side))
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=88)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def chat(prompt: str, *, model: str = DEFAULT_MODEL, media: list[str] | None = None,
         schema: dict | None = None, cpu: bool = False, max_tokens: int = 2048,
         timeout: float = 900) -> dict:
    """One non-streamed turn. Returns {text, timings, model}."""
    message = {"role": "user", "content": prompt}
    if media:
        message["images"] = list(media)
    options = {"temperature": 0, "seed": SEED, "num_ctx": 16384,
               "num_predict": max_tokens}
    if cpu:
        options["num_gpu"] = 0
    body = {"model": model, "messages": [message], "stream": False,
            "think": False, "keep_alive": "15m", "options": options}
    if schema is not None:
        body["format"] = schema

    req = urllib.request.Request(
        f"{BASE_URL.rstrip('/')}/api/chat",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read()[:300].decode("utf-8", "replace")
        raise ModelError(f"Ollama refused the request (HTTP {exc.code}): {detail}") from exc
    except OSError as exc:
        raise ModelError(f"no Ollama server at {BASE_URL} ({exc}). Start Ollama "
                         f"and run `ollama pull {model}`.") from exc

    if data.get("done_reason") == "length":
        raise ModelError(f"answer hit the {max_tokens}-token limit and was cut off")
    text = (data.get("message") or {}).get("content") or ""
    if not text.strip():
        raise ModelError("model returned an empty answer")
    ns = 1e9
    timings = {
        "total_s": round(data.get("total_duration", 0) / ns, 2),
        "load_s": round(data.get("load_duration", 0) / ns, 2),
        "prompt_s": round(data.get("prompt_eval_duration", 0) / ns, 2),
        "generate_s": round(data.get("eval_duration", 0) / ns, 2),
        "prompt_tokens": data.get("prompt_eval_count", 0),
        "output_tokens": data.get("eval_count", 0),
    }
    return {"text": text, "timings": timings, "model": model}


TRANSCRIBE_PROMPT = (
    "Transcribe this voice note exactly as spoken, in the language spoken. "
    "Output only the transcript. If it is not in English, add a final line "
    "starting 'English:' with a translation. If there is no speech, output "
    "[no speech].")


def transcribe(chunks: list[str], *, model: str = DEFAULT_MODEL,
               cpu: bool = False) -> dict:
    """Transcribe a memo given as base64 WAV chunks. Returns {text, timings}."""
    texts, timings = [], []
    for chunk in chunks:
        r = chat(TRANSCRIBE_PROMPT, model=model, media=[chunk], cpu=cpu,
                 max_tokens=1024)
        texts.append(r["text"].strip())
        timings.append(r["timings"])
    return {"text": " ".join(t for t in texts if t and t != "[no speech]"),
            "timings": timings}


def checklist(prompt: str, photos_b64: list[str], schema: dict, *,
              model: str = DEFAULT_MODEL, cpu: bool = False) -> dict:
    """Ask for the checklist as schema-shaped JSON. Returns {raw, timings}."""
    r = chat(prompt, model=model, media=photos_b64, schema=schema, cpu=cpu)
    try:
        raw = json.loads(r["text"])
    except json.JSONDecodeError as exc:
        raise ModelError(f"checklist was not valid JSON: {r['text'][:200]}") from exc
    return {"raw": raw, "timings": r["timings"]}
