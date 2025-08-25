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
# Config
# ─────────────────────────────────────────────────────────────
st.set_page_config(page_title='Meditation Chimes', page_icon='🧘', layout='centered')
TZ = ZoneInfo('America/New_York')  # US/Eastern
SR = 44100  # audio sample rate

# ─────────────────────────────────────────────────────────────
# Audio synthesis helpers (procedural bowls/gongs)
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
    school_bell_synth = synth_tone([(880, 0.9), (1760, 0.5), (2637, 0.25)], duration=0.6, decay=6.0)
    return {
        "Soft Bell": (synth_tone([(660, 0.6), (990, 0.4), (1320, 0.2)], duration=2.2, decay=2.0), 'audio/wav'),
        "Singing Bowl": (synth_tone([(196, 0.8), (392, 0.35), (294, 0.25)], duration=3.0, decay=1.1), 'audio/wav'),
        "Wood Block": (synth_tone([(880, 1.0)], duration=0.35, decay=6.5), 'audio/wav'),
        "School Bell (synthetic)": (school_bell_synth, 'audio/wav'),
    }


def generate_gongs_and_bowls(n=100, seed=7):
    rng = np.random.default_rng(seed)
    sounds = {}
    categories = [
        ("Deep Gong", 90, 2.5), ("Bronze Gong", 140, 2.2), ("Temple Gong", 220, 2.0),
        ("Singing Bowl", 196, 1.3), ("Wind Chime", 660, 3.5)
    ]
    for i in range(n):
        name_base, base_freq, decay = categories[i % len(categories)]
        partials = []
        num_partials = rng.integers(3, 6)
        for k in range(1, num_partials + 1):
            detune = rng.normal(0, 0.015)
            amp = max(0.15, 1.2 / (k + rng.random()))
            partials.append(((base_freq * k) * (1 + detune), amp))
        wav = synth_tone(partials, duration=2.0 + float(rng.random() * 1.5), decay=decay)
        sounds[f"{name_base} #{i+1}"] = (wav, 'audio/wav')
    return sounds

@st.cache_data(show_spinner=False, ttl=60*60*24)
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

def audio_player_autoplay(audio_bytes, mime='audio/wav', key='aplayer', repeat_seconds=1):
    b64 = base64.b64encode(audio_bytes).decode()
    html = f"""
    <audio id='{key}' autoplay loop>
      <source src='data:{mime};base64,{b64}'>
    </audio>
    <script>
      const a = document.getElementById('{key}');
      a.play().catch(() => {{
        const resume = () => {{ a.play(); document.removeEventListener('click', resume); }};
        document.addEventListener('click', resume);
      }});
      setTimeout(() => {{ try {{ a.loop = false; a.pause(); a.currentTime = 0; }} catch (e) {{}} }}, {1000} * {max(1, repeat_seconds)});
    </script>
    """
    st.components.v1.html(html, height=0)

if 'sounds' not in st.session_state:
    lib = {}
    lib.update(builtin_sounds_base())
    lib.update(generate_gongs_and_bowls(100))
    local_bell = '/mnt/data/hailuoto-school-bell-recording-106632.mp3'
    if os.path.exists(local_bell):
        try:
            with open(local_bell, 'rb') as f:
                lib['School Bell'] = (f.read(), 'audio/mpeg')
        except Exception:
            pass
    gh_blob_url = 'https://github.com/vinayakagude/Alarm/blob/main/hailuoto-school-bell-recording-106632.mp3'
    raw_url = to_raw_github_url(gh_blob_url)
    content = fetch_remote_bytes(raw_url)
    if content:
        lib['School Bell'] = (content, 'audio/mpeg')
    st.session_state.sounds = lib

if 'timers' not in st.session_state:
    st.session_state.timers = []
if 'running' not in st.session_state:
    st.session_state.running = True

st.title('🧘 Meditation Chimes — Day Planner')
st.caption('US/Eastern time. Create a start–end window, choose the interval, sound, and how long each chime plays.')

with st.sidebar:
    st.header('Preview & Settings')
    st.toggle('Running', value=st.session_state.running, key='running')
    preview_name = st.selectbox('Preview a sound', list(st.session_state.sounds.keys()))
    preview_secs = st.slider('Preview length (sec)', 1, 20, 4)
    if st.button('▶️ Preview'):
        snd = st.session_state.sounds[preview_name]
        data, mime = snd if isinstance(snd, tuple) else (snd, 'audio/wav')
        audio_player_autoplay(data, mime, key='preview', repeat_seconds=preview_secs)
    st.divider()
    st.subheader('Add remote sound via URL')
    default_url = 'https://github.com/vinayakagude/Alarm/blob/main/hailuoto-school-bell-recording-106632.mp3'
    user_url = st.text_input('Paste a direct file or GitHub blob URL', default_url)
    if st.button('Add Remote Sound') and user_url.strip():
        raw_u = to_raw_github_url(user_url.strip())
        data = fetch_remote_bytes(raw_u)
        if data:
            name = os.path.basename(raw_u)
            st.session_state.sounds[f'Remote: {name}'] = (data, 'audio/mpeg')
            st.success(f'Added remote sound: {name}')
        else:
            st.warning('Could not fetch that URL. Make sure it is publicly accessible.')

with st.form('add_block'):
    st.subheader('Create a Chime Schedule')
    label = st.text_input('Label', 'Meditation')
    c1, c2, c3 = st.columns(3)
    start_time = c1.time_input('Start time', dt.time(9, 0))
    end_time = c2.time_input('End time', dt.time(17, 0))
    interval_min = c3.number_input('Repeat every (min)', 1, 1, 1)
    c4, c5 = st.columns(2)
    sound_name = c4.selectbox('Chime sound', list(st.session_state.sounds.keys()))
    play_seconds = c5.number_input('Each alarm plays (sec)', 1, 300, 5)
    repeat_daily = st.checkbox('Repeat daily', True)
    submitted = st.form_submit_button('Add Schedule')
    if submitted:
        if end_time <= start_time:
            st.error('End time must be after start time.')
        else:
            new_id = int(time.time() * 1000)
            st.session_state.timers.append({
                'id': new_id,
                'label': label.strip(),
                'start': start_time.strftime('%H:%M'),
                'end': end_time.strftime('%H:%M'),
                'interval_min': int(interval_min),
                'sound': sound_name,
                'play_seconds': int(play_seconds),
                'repeat_daily': bool(repeat_daily),
                'last_day': None,
                'fired': [],
            })
            st.success(f"Schedule added!")
