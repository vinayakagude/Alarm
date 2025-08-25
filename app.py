import streamlit as st
import datetime as dt
import time
import base64
import io
import wave
import numpy as np

# ─────────────────────────────────────────────────────────────
# Audio synthesis helpers
# ─────────────────────────────────────────────────────────────
SR = 44100  # sample rate


def synth_tone(freqs, duration=2.0, decay=2.0):
    """Synthesize a simple struck tone with multiple partials.
    freqs: list of (frequency, amplitude)
    returns WAV bytes
    """
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
    """Procedurally generate ~100 distinct gong/meditation tones."""
    rng = np.random.default_rng(seed)
    sounds = {}
    # Distribute names across categories
    categories = [
        ("Deep Gong", 90, 2.5),
        ("Bronze Gong", 140, 2.2),
        ("Temple Gong", 220, 2.0),
        ("Singing Bowl", 196, 1.3),
        ("Wind Chime", 660, 3.5),
    ]
    for i in range(n):
        name_base, base_freq, decay = categories[i % len(categories)]
        # Create 3–5 partials with random detuning and amplitudes
        partials = []
        num_partials = rng.integers(3, 6)
        for k in range(1, num_partials + 1):
            detune = rng.normal(0, 0.015)  # ~1.5% detune
            amp = max(0.15, 1.2 / (k + rng.random()))
            partials.append(((base_freq * k) * (1 + detune), amp))
        duration = 2.0 + float(rng.random() * 1.5)
        wav = synth_tone(partials, duration=duration, decay=decay)
        sounds[f"{name_base} #{i+1}"] = (wav, 'audio/wav')
    return sounds


# ─────────────────────────────────────────────────────────────
# UI helpers
# ─────────────────────────────────────────────────────────────

def audio_player_autoplay(audio_bytes: bytes, mime: str = 'audio/wav', key: str = 'aplayer', repeat_seconds: int = 1):
    """Render <audio> that loops until repeat_seconds elapse (by replaying from 0)."""
    b64 = base64.b64encode(audio_bytes).decode()
    html = f"""
    <audio id='{key}' autoplay>
      <source src='data:{mime};base64,{b64}'>
    </audio>
    <script>
      const a = document.getElementById('{key}');
      const endTime = Date.now() + {repeat_seconds * 1000};
      function replay() {{
        if (Date.now() < endTime) {{
          a.currentTime = 0; a.play().catch(()=>{{}});
        }}
      }}
      a.addEventListener('ended', replay);
      a.play().catch(() => {{
        const resume = () => {{ a.play(); document.removeEventListener('click', resume); }};
        document.addEventListener('click', resume);
      }});
    </script>
    """
    st.components.v1.html(html, height=0)


def auto_refresh(interval_ms=1000):
    """Trigger a rerun by nudging the querystring every interval."""
    st.components.v1.html(
        f"""
        <script>
        setTimeout(function() {{
            const url = new URL(window.location);
            url.searchParams.set('ts', Date.now());
            window.location.replace(url.toString());
        }}, {interval_ms});
        </script>
        """,
        height=0,
    )


# ─────────────────────────────────────────────────────────────
# Session state
# ─────────────────────────────────────────────────────────────
if 'sounds' not in st.session_state:
    lib = {}
    lib.update(builtin_sounds_base())
    lib.update(generate_gongs_and_bowls(100))  # +100 procedurally generated tones
    st.session_state.sounds = lib  # name -> (bytes, mime)

if 'timers' not in st.session_state:
    # each timer: block with schedule across a time window
    # {id, label, start_hm, end_hm, interval_min, sound_name, play_seconds, repeat_daily, last_day, fired_times}
    st.session_state.timers = []

if 'running' not in st.session_state:
    st.session_state.running = True

st.set_page_config(page_title='Meditation Chimes', page_icon='🧘', layout='centered')

st.title('🧘 Meditation Chimes — Day Planner')
st.caption('Select a start & end time, how often to chime, and how long each chime should play. Upload your own sounds too.')

# Sidebar
with st.sidebar:
    st.header('Playback & Library')
    st.toggle('Running', value=st.session_state.running, key='running')

    st.subheader('Preview a Sound')
    preview_name = st.selectbox('Choose a sound to preview', list(st.session_state.sounds.keys()))
    preview_secs = st.slider('Preview length (sec)', 1, 20, 4)
    if st.button('▶️ Preview'):
        data, mime = st.session_state.sounds[preview_name]
        audio_player_autoplay(data, mime, key='preview', repeat_seconds=preview_secs)

    st.subheader('Add Custom Sound')
    up = st.file_uploader('Upload WAV/MP3/OGG/M4A', type=['wav', 'mp3', 'ogg', 'm4a'])
    custom_name = st.text_input('Name your sound', '')
    if st.button('Add Sound'):
        if up and custom_name.strip():
            data = up.read()
            mime = up.type or 'audio/mpeg'
            st.session_state.sounds[custom_name.strip()] = (data, mime)
            st.success(f'Added "{custom_name.strip()}"')
        else:
            st.warning('Please provide a file and a name.')

# New timer form (block scheduler)
with st.form('add_block'):
    st.subheader('Create a Chime Schedule')
    label = st.text_input('Label (optional)', placeholder='Mindful breaks')

    c1, c2, c3 = st.columns(3)
    start_time = c1.time_input('Start time', dt.time(9, 0), step=60)
    end_time = c2.time_input('End time', dt.time(17, 0), step=60)
    interval_min = c3.number_input('Repeat every (min)', min_value=1, max_value=240, value=60)

    c4, c5, c6 = st.columns(3)
    sound_name = c4.selectbox('Chime sound', list(st.session_state.sounds.keys()))
    play_seconds = c5.number_input('How long should each alarm be (sec)?', min_value=1, max_value=300, value=5)
    repeat_daily = c6.checkbox('Repeat daily', value=True)

    submitted = st.form_submit_button('Add Schedule')
    if submitted:
        if end_time <= start_time:
            st.error('End time must be after start time.')
        else:
            new_id = int(time.time() * 1000)
            st.session_state.timers.append({
                'id': new_id,
                'label': (label or 'Meditation').strip(),
                'start_hm': start_time.strftime('%H:%M'),
                'end_hm': end_time.strftime('%H:%M'),
                'interval_min': int(interval_min),
                'sound_name': sound_name,
                'play_seconds': int(play_seconds),
                'repeat_daily': bool(repeat_daily),
                'last_day': None,
                'fired_times': [],  # list of 'HH:MM'
            })
            st.success('Schedule added!')

# List schedules
st.subheader("Today's Schedules")

remove_ids = []
for t in st.session_state.timers:
    # Compute the planned hits for today
    hh_s, mm_s = map(int, t['start_hm'].split(':'))
    hh_e, mm_e = map(int, t['end_hm'].split(':'))
    today = dt.datetime.now().replace(second=0, microsecond=0)
    start_dt = today.replace(hour=hh_s, minute=mm_s)
    end_dt = today.replace(hour=hh_e, minute=mm_e)

    hits = []
    cur = start_dt
    while cur <= end_dt:
        hits.append(cur.strftime('%H:%M'))
        cur += dt.timedelta(minutes=t['interval_min'])

    col1, col2 = st.columns([3, 2])
    with col1:
        st.write(f"**{t['label']}** • {t['start_hm']} → {t['end_hm']} • every {t['interval_min']} min • {t['play_seconds']}s • {t['sound_name']}")
    with col2:
        if st.button('✖️ Delete', key=f'del_{t["id"]}'):
            remove_ids.append(t['id'])
    st.caption('Times today: ' + ', '.join(hits))

if remove_ids:
    st.session_state.timers = [x for x in st.session_state.timers if x['id'] not in remove_ids]
    st.success('Removed schedule(s).')

st.divider()

# Clock + triggering
now = dt.datetime.now()
st.metric('Current Time', now.strftime('%A, %b %d — %I:%M:%S %p'))

if st.session_state.running:
    auto_refresh(1000)

for t in st.session_state.timers:
    today_str = now.strftime('%Y-%m-%d')
    # Reset fired list at day change or when repeat_daily is True
    if t['last_day'] != today_str:
        t['fired_times'] = []
        t['last_day'] = today_str

    hh_s, mm_s = map(int, t['start_hm'].split(':'))
    hh_e, mm_e = map(int, t['end_hm'].split(':'))
    start_dt = now.replace(hour=hh_s, minute=mm_s, second=0, microsecond=0)
    end_dt = now.replace(hour=hh_e, minute=mm_e, second=59, microsecond=0)

    if start_dt <= now <= end_dt:
        # Determine the current scheduled minute bucket
        total_min_since_start = int((now - start_dt).total_seconds() // 60)
        if total_min_since_start % int(t['interval_min']) == 0:
            hit_hm = now.strftime('%H:%M')
            if hit_hm not in t['fired_times']:
                data, mime = st.session_state.sounds[t['sound_name']]
                st.success(f"Time for: {t['label']} ({hit_hm})")
                audio_player_autoplay(data, mime, key=f"play_{t['id']}_{hit_hm}", repeat_seconds=int(t['play_seconds']))
                t['fired_times'].append(hit_hm)

# Friendly hint
if not st.session_state.timers:
    st.info('No schedules yet. Add one above!')

st.caption('Tip: Keep this tab open. Some browsers require one interaction to enable autoplay audio.')
