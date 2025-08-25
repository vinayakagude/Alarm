import streamlit as st
import datetime as dt
import time
import base64
import io
import wave
import numpy as np
from zoneinfo import ZoneInfo
import os
import requests

# ─────────────────────────────────────────────────────────────
# App config
# ─────────────────────────────────────────────────────────────
st.set_page_config(page_title='Meditation Chimes', page_icon='🧘', layout='centered')
TZ = ZoneInfo('America/New_York')   # US/Eastern
SR = 44100                          # audio sample rate

# ─────────────────────────────────────────────────────────────
# Audio synthesis helpers
# ─────────────────────────────────────────────────────────────

def synth_tone(freqs, duration=2.0, decay=2.0):
    t = np.linspace(0, duration, int(SR * duration), endpoint=False)
    y = np.zeros_like(t)
    for f, a in freqs:
        y += a * np.sin(2 * np.pi * f * t)
    env = np.exp(-t * decay)
    y = y * env
    y /= max(1e-9, np.max(np.abs(y)))
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SR)
        wf.writeframes((y * 32767).astype('<i2').tobytes())
    return buf.getvalue()


def builtin_sounds_base():
    bell = synth_tone([(880, 0.9), (1760, 0.5), (2637, 0.25)], duration=0.6, decay=6.0)
    return {
        "Soft Bell": (synth_tone([(660, 0.6), (990, 0.4), (1320, 0.2)], duration=2.2, decay=2.0), 'audio/wav'),
        "Singing Bowl": (synth_tone([(196, 0.8), (392, 0.35), (294, 0.25)], duration=3.0, decay=1.1), 'audio/wav'),
        "Wood Block": (synth_tone([(880, 1.0)], duration=0.35, decay=6.5), 'audio/wav'),
        "School Bell (synthetic)": (bell, 'audio/wav'),
    }


def generate_gongs_and_bowls(n=100, seed=7):
    rng = np.random.default_rng(seed)
    sounds = {}
    categories = [
        ("Deep Gong", 90, 2.5), ("Bronze Gong", 140, 2.2), ("Temple Gong", 220, 2.0),
        ("Singing Bowl", 196, 1.3), ("Wind Chime", 660, 3.5)
    ]
    for i in range(n):
        name, base, decay = categories[i % len(categories)]
        parts = []
        for k in range(1, rng.integers(3, 6) + 1):
            det = rng.normal(0, 0.015)
            amp = max(0.15, 1.2 / (k + rng.random()))
            parts.append(((base * k) * (1 + det), amp))
        wav = synth_tone(parts, 2.0 + float(rng.random() * 1.5), decay)
        sounds[f"{name} #{i+1}"] = (wav, 'audio/wav')
    return sounds

# ─────────────────────────────────────────────────────────────
# Remote sound helpers (GitHub raw URLs, etc.)
# ─────────────────────────────────────────────────────────────

@st.cache_data(ttl=86400)
def fetch_remote_bytes(url: str):
    try:
        r = requests.get(url, timeout=10)
        if r.status_code == 200 and r.content:
            return r.content
    except Exception:
        return None
    return None


def to_raw_github_url(blob_url: str) -> str:
    if 'github.com/' in blob_url and '/blob/' in blob_url:
        return blob_url.replace('github.com/', 'raw.githubusercontent.com/').replace('/blob/', '/')
    return blob_url

# ─────────────────────────────────────────────────────────────
# Audio player for preview only
# ─────────────────────────────────────────────────────────────

def audio_player_preview(audio_bytes, mime='audio/wav', key='aplayer'):
    b64 = base64.b64encode(audio_bytes).decode()
    html = f"""
    <audio id='{key}' controls>
      <source src='data:{mime};base64,{b64}'>
    </audio>
    """
    st.components.v1.html(html, height=60)

# ─────────────────────────────────────────────────────────────
# Session state
# ─────────────────────────────────────────────────────────────
if 'sounds' not in st.session_state:
    lib = {}
    lib.update(builtin_sounds_base())
    lib.update(generate_gongs_and_bowls(100))
    st.session_state.sounds = lib

# ─────────────────────────────────────────────────────────────
# UI
# ─────────────────────────────────────────────────────────────
st.title('🧘 Meditation Chimes — Preview Only')
st.caption('US/Eastern time. You can preview sounds, but scheduled alarms are disabled.')

# Client‑side clock (smooth second tick)
clock_html = """
<div id=\"et-clock\" style=\"font-size:1.2rem;margin:.25rem 0 1rem 0;font-family: ui-monospace, monospace;\"></div>
<script>
function pad(n){return n<10?('0'+n):n}
function tick(){
  try{
    const now=new Date();
    const et=new Date(now.toLocaleString('en-US',{timeZone:'America/New_York'}));
    const wd=et.toLocaleDateString('en-US',{weekday:'long'});
    const mon=et.toLocaleDateString('en-US',{month:'short'});
    const d=et.getDate();
    const h12=((et.getHours()+11)%12)+1;
    const mm=pad(et.getMinutes());
    const ss=pad(et.getSeconds());
    const ap=et.getHours()>=12?'PM':'AM';
    document.getElementById('et-clock').textContent=`${wd}, ${mon} ${d} — ${pad(h12)}:${mm}:${ss} ${ap} ET`;
  }catch(e){}
}
tick(); setInterval(tick,1000);
</script>
"""
st.components.v1.html(clock_html, height=36)

with st.sidebar:
    st.header('Preview Sounds')
    preview = st.selectbox('Choose a sound', list(st.session_state.sounds.keys()))
    if st.button('▶️ Play Preview'):
        d, m = st.session_state.sounds[preview] if isinstance(st.session_state.sounds[preview], tuple) else (st.session_state.sounds[preview], 'audio/wav')
        audio_player_preview(d, m, key='preview')
