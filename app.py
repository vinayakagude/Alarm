import streamlit as st
import datetime as dt
import time
import base64
import io
import wave
import numpy as np
from zoneinfo import ZoneInfo

SR = 44100

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
    return {
        "Soft Bell": (synth_tone([(660, 0.6), (990, 0.4), (1320, 0.2)], duration=2.2, decay=2.0), 'audio/wav'),
        "Singing Bowl": (synth_tone([(196, 0.8), (392, 0.35), (294, 0.25)], duration=3.0, decay=1.1), 'audio/wav'),
        "Wood Block": (synth_tone([(880, 1.0)], duration=0.35, decay=6.5), 'audio/wav'),
    }

def generate_gongs_and_bowls(n=100, seed=7):
    rng = np.random.default_rng(seed)
    sounds = {}
    categories = [("Deep Gong", 90, 2.5), ("Bronze Gong", 140, 2.2), ("Temple Gong", 220, 2.0), ("Singing Bowl", 196, 1.3), ("Wind Chime", 660, 3.5)]
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

# ▶️ Robust looping audio: use the <audio loop> attribute and stop it after N seconds
# This works even when the sound is longer than repeat_seconds.

def audio_player_autoplay(audio_bytes, mime='audio/wav', key='aplayer', repeat_seconds=1):
    b64 = base64.b64encode(audio_bytes).decode()
    html = f"""
    <audio id='{key}' autoplay loop>
      <source src='data:{mime};base64,{b64}'>
    </audio>
    <script>
      const a = document.getElementById('{key}');
      // Start playback; if blocked, resume on first user interaction
      a.play().catch(() => {{
        const resume = () => {{ a.play(); document.removeEventListener('click', resume); }};
        document.addEventListener('click', resume);
      }});
      // Stop looping after the requested duration
      setTimeout(() => {{
        try {{
          a.loop = false;
          a.pause();
          a.currentTime = 0;
        }} catch (e) {{}}
      }}, {max(1, int(1000)) if isinstance(1000, int) else 1000} * {repeat_seconds});
    </script>
    """
    st.components.v1.html(html, height=0)

def auto_refresh(interval_ms=1000):
    st.components.v1.html(f"<script>setTimeout(function(){{const url=new URL(window.location);url.searchParams.set('ts',Date.now());window.location.replace(url.toString());}},{interval_ms});</script>",height=0)

if 'sounds' not in st.session_state:
    lib = {}
    lib.update(builtin_sounds_base())
    lib.update(generate_gongs_and_bowls(100))
    st.session_state.sounds = lib

if 'timers' not in st.session_state:
    st.session_state.timers = []

if 'running' not in st.session_state:
    st.session_state.running = True

st.set_page_config(page_title='Meditation Chimes', page_icon='🧘', layout='centered')

st.title('🧘 Meditation Chimes — Day Planner')

with st.sidebar:
    st.header('Preview')
    st.toggle('Running', value=st.session_state.running, key='running')
    preview_name = st.selectbox('Preview sound', list(st.session_state.sounds.keys()))
    secs = st.slider('Preview seconds', 1, 20, 4)
    if st.button('▶️ Preview'):
        snd = st.session_state.sounds[preview_name]
        data, mime = snd if isinstance(snd, tuple) else (snd, 'audio/wav')
        audio_player_autoplay(data, mime, key='preview', repeat_seconds=secs)

with st.form('add_block'):
    st.subheader('Add Schedule')
    label = st.text_input('Label', 'Meditation')
    c1, c2, c3 = st.columns(3)
    start_time = c1.time_input('Start time', dt.time(9,0))
    end_time = c2.time_input('End time', dt.time(17,0))
    interval_min = c3.number_input('Repeat every (min)',1,240,60)
    c4, c5 = st.columns(2)
    sound_name = c4.selectbox('Chime sound', list(st.session_state.sounds.keys()))
    play_seconds = c5.number_input('Duration (sec)',1,300,5)
    repeat_daily = st.checkbox('Repeat daily',True)
    submitted = st.form_submit_button('Add')
    if submitted:
        new_id=int(time.time()*1000)
        st.session_state.timers.append({
            'id':new_id,
            'label':label.strip(),
            'start':start_time.strftime('%H:%M'),
            'end':end_time.strftime('%H:%M'),
            'interval_min':int(interval_min),
            'sound':sound_name,
            'play_seconds':int(play_seconds),
            'repeat_daily':repeat_daily,
            'last_day':None,
            'fired':[]
        })
        st.success('Schedule added!')

st.subheader("Today's Schedules")
remove_ids=[]
for t in st.session_state.timers:
    st.write(f"**{t['label']}** {t['start']}→{t['end']} every {t['interval_min']}m {t['play_seconds']}s {t['sound']}")
    if st.button('Delete',key=f"del{t['id']}"): remove_ids.append(t['id'])
if remove_ids:
    st.session_state.timers=[x for x in st.session_state.timers if x['id'] not in remove_ids]

now = dt.datetime.now(ZoneInfo("America/New_York"))
st.metric('Current Time (US/Eastern)', now.strftime('%A, %b %d — %I:%M:%S %p'))
if st.session_state.running: auto_refresh(1000)

today=now.strftime('%Y-%m-%d')
for t in st.session_state.timers:
    if t['last_day']!=today:
        t['fired']=[]; t['last_day']=today
    hh_s,mm_s=map(int,t['start'].split(':'))
    hh_e,mm_e=map(int,t['end'].split(':'))
    start_dt=now.replace(hour=hh_s,minute=mm_s,second=0,microsecond=0)
    end_dt=now.replace(hour=hh_e,minute=mm_e,second=59,microsecond=0)
    if start_dt<=now<=end_dt:
        elapsed=int((now-start_dt).total_seconds()//60)
        if elapsed%t['interval_min']==0:
            hm=now.strftime('%H:%M')
            if hm not in t['fired']:
                snd=st.session_state.sounds[t['sound']]
                data,mime=snd if isinstance(snd,tuple) else (snd,'audio/wav')
                st.success(f"Time for: {t['label']} {hm}")
                audio_player_autoplay(data,mime,key=f"p{t['id']}{hm}",repeat_seconds=t['play_seconds'])
                t['fired'].append(hm)
if not st.session_state.timers:
    st.info('No schedules yet')
