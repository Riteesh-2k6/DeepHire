"""Opt-in camera-setup check: one still frame to a local vision model, back come setup tips.

About the room, never the person: the prompt forbids it and a word filter enforces it in code.
The frame is only held in memory for the call.
"""
import base64
import os
import re

import requests

from answer_evaluator import chat_json, within

VISION_MODEL = os.getenv("VISION_MODEL", "qwen2.5-vl-3b")
MAX_TIPS = 4
DEADLINE_S = 150  # first use loads the model (about a minute on CPU); later checks take ~5 s

PROMPT = """This is a webcam frame from someone about to practise a video interview.
Give two to four short, practical tips about the SETUP only: lighting (too dark, backlit, uneven),
framing (head too high, low, close, far or off-centre), camera height and eye line, and a distracting
background. Base every tip on something you can actually see in THIS frame and name it (for example
"the bright window behind you"); no generic advice. If something is already good, say so in one tip.
Never describe or judge the person: no comments on their face, expression, mood, emotions,
confidence, appearance, clothing, age, gender, body or ethnicity.
Reply with JSON only: {"tips": ["...", "..."]}"""

# Any tip touching the person rather than the room is dropped, whatever the model meant.
BANNED = re.compile(
    r"\b(emotion\w*|mood|feel\w*|happy|sad|angry|nervous\w*|anxious|anxiety|confiden\w*|stress\w*|tired|"
    r"smil\w*|frown\w*|expression\w*|awkward\w*|attractive\w*|pretty|handsome|beautiful|ugly|young|old|age|gender|"
    r"male|female|man|woman|race|ethnic\w*|skin|hair\w*|beard|makeup|weight|fat|thin|outfit|cloth\w*|shirt|dress\w*)\b",
    re.I)


def keep_setup_tips(tips):
    """Strings only, room-only, de-duplicated, at most MAX_TIPS."""
    out = []
    for tip in tips if isinstance(tips, list) else []:
        tip = re.sub(r"\s+", " ", str(tip)).strip(" -•*")
        if 4 <= len(tip) <= 200 and not BANNED.search(tip) and tip not in out:
            out.append(tip)
    return out[:MAX_TIPS]


def check_frame(jpeg_bytes, post=requests.post):
    """Returns {"tips": [...]} or {"error": "..."}."""
    image = "data:image/jpeg;base64," + base64.b64encode(jpeg_bytes).decode()
    messages = [{"role": "user", "content": [
        {"type": "text", "text": PROMPT},
        {"type": "image_url", "image_url": {"url": image}},
    ]}]
    try:
        result = within(DEADLINE_S, chat_json, messages, model=VISION_MODEL, max_tokens=300, timeout=DEADLINE_S, post=post)
    except requests.RequestException as e:
        return {"error": f"The vision model '{VISION_MODEL}' didn't answer ({type(e).__name__}). Is it set up in llama-swap?"}
    except ValueError:
        return {"error": "The vision model returned something that wasn't the expected JSON."}
    if result is None:
        return {"error": f"The vision model took longer than {DEADLINE_S} s. Try again in a minute; the first check loads it."}
    tips = keep_setup_tips(result.get("tips") if isinstance(result, dict) else None)
    return {"tips": tips} if tips else {"error": "The vision model gave no usable setup tips."}
