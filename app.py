import streamlit as st
import datetime as dt
import time
import base64
import io
import wave
import numpy as np

# --- Helpers to synthesize simple built‑in chimes (WAV bytes) ---
SR = 44100  # sample rate

def synth_tone(freqs, duration=1.5, decay=2.5):
    t = np.linspace(0, duration, int(SR * duration), endpoint=False)
    wave_sum = np.zeros_like(t)
    for f, amp in freqs:
        wave_sum += amp * np.sin(2 * np.pi * f * t)
    env = np.exp(-t * decay)
    audio = (wave_sum * env)
    # normalize
    audio /= max(1e-9, np.max(np.abs(audio)))
    # to 16-bit PCM WAV in-memory
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SR)
        wf.writeframes((audio * 32767).astype('<i2').tobytes())
    return buf.getvalue()

def builtin_sounds():
    return {
        "Soft Bell": synth_tone([(660, 0.6), (990, 0.4), (1320, 0.2)], duration=2.2, decay=2.0),
        "Singing Bowl": synth_tone([(196, 0.8), (392, 0.35), (294, 0.25)], duration=3.0, decay=1.1),
        "Wood Block": synth_tone([(880, 1.0)], duration=0.35, decay=6.5),
    }

# --- Audio rendering (autoplay) ---

def audio_player_autoplay(audio_bytes: bytes, mime: str = 'audio/wav', key: str = 'aplayer'):
    b64 = base64.b64encode(audio_bytes).decode()
    html = f"""
    <audio id='{key}' autoplay>
      <source src='data:{mime};base64,{b64}'>
    </audio>
    <script>
      // Attempt to resume playback if browser blocks autoplay until interaction
      const a = document.getElementById('{key}');
      a.play().catch(() => {{
        const resume = () => {{ a.play(); document.removeEventListener('click', resume); }};
        document.addEventListener('click', resume);
      }});
    </script>
    """
    st.components.v1.html(html, height=0)

# --- Session state setup ---
if 'sounds' not in st.session_state:
    st.session_state.sounds = {name: data for name, data in builtin_sounds().items()}
if 'custom_sounds' not in st.session_state:
    st.session_state.custom_sounds = {}
if 'timers' not in st.session_state:
    # each timer: {id, label, time_hm, sound_name, repeat, last_fired_date}
    st.session_state.timers = []
if 'running' not in st.session_state:
    st.session_state.running = True
if 'tz' not in st.session_state:
    st.session_state.tz = 'America/New_York'

st.set_page_config(page_title='Meditation Chimes', page_icon='🧘', layout='centered')

st.title('🧘 Meditation Chimes — Day Planner')
st.caption('Set quiet reminders throughout your day with gentle chime sounds. Add your own audio if you like.')

# --- Sidebar controls ---
with st.sidebar:
    st.header('Settings')
    tz = st.text_input('Timezone (IANA name)', st.session_state.tz, help='e.g., America/New_York, Europe/London, Asia/Kolkata')
    st.session_state.tz = tz
    st.toggle('Running', value=st.session_state.running, key='running')

    st.divider()
    st.subheader('Built‑in Sounds')
    for name in list(builtin_sounds().keys()):
        if st.button(f'▶️ Play {name}', key=f'play_{name}'):
            audio_player_autoplay(st.session_state.sounds[name])

    st.subheader('Add Custom Sound')
    up = st.file_uploader('Upload WAV/MP3/OGG/M4A', type=['wav', 'mp3', 'ogg', 'm4a'], accept_multiple_files=False)
    custom_name = st.text_input('Name your sound', '')
    if st.button('Add Sound'):
        if up and custom_name:
            data = up.read()
            # we keep original mime if possible
            mime = up.type or 'application/octet-stream'
            # store as (bytes, mime)
            st.session_state.custom_sounds[custom_name] = (data, mime)
            st.session_state.sounds[custom_name] = data  # default assume browser sniffs
            st.success(f'Added "{custom_name}"')
        else:
            st.warning('Please choose a file and provide a name.')

# --- New timer form ---
with st.form('add_timer'):
    st.subheader('Add a Meditation Time')
    cols = st.columns([2, 1])
    label = cols[0].text_input('Label (optional)', placeholder='Mid‑morning pause')
    time_hm = cols[1].time_input('Time (HH:MM)', dt.time(9, 0), step=60)

    sound_name = st.selectbox('Chime Sound', list(st.session_state.sounds.keys()))
    repeat = st.checkbox('Repeat daily', value=True)
    submitted = st.form_submit_button('Add to Schedule')

    if submitted:
        new_id = int(time.time() * 1000)
        st.session_state.timers.append({
            'id': new_id,
            'label': label.strip() or 'Meditation',
            'time_hm': time_hm.strftime('%H:%M'),
            'sound_name': sound_name,
            'repeat': repeat,
            'last_fired_date': None,
        })
        st.success('Timer added!')

# --- Manage existing timers ---
st.subheader("Today's Schedule")

# Sort by time
st.session_state.timers.sort(key=lambda x: x['time_hm'])

remove_ids = []
for tmr in st.session_state.timers:
    col1, col2, col3, col4, col5 = st.columns([2, 1.2, 1.6, 1.2, 0.8])
    col1.write(tmr['label'])
    col2.write(tmr['time_hm'])
    col3.write(('🔁 Daily' if tmr['repeat'] else '• One‑time'))
    col4.write(tmr['sound_name'])
    if col5.button('✖️', key=f'del_{tmr["id"]}'):
        remove_ids.append(tmr['id'])

if remove_ids:
    st.session_state.timers = [t for t in st.session_state.timers if t['id'] not in remove_ids]
    st.success('Removed selected timer(s).')

st.divider()

# --- Timekeeping & triggering ---
# We refresh the app once per second while running
if st.session_state.running:
    st.autorefresh = st.experimental_singleton(lambda: True)
    st.experimental_rerun  # no-op to appease linters
    st_autorefresh = st.sidebar.empty()
    st_autorefresh.write('⏱️ Auto‑refreshing each second while running…')
    st.experimental_set_query_params(ts=int(time.time()))
    st.empty()

# To actually refresh, use st_autorefresh API
if st.session_state.running:
    st_autorefresh_count = st.experimental_get_query_params().get('ref', [0])[0]
    st_autorefresh_count = int(st_autorefresh_count) if isinstance(st_autorefresh_count, str) else 0
    st.experimental_set_query_params(ref=str(st_autorefresh_count + 1))

# Current time display (based on selected timezone; informational only)
now_local = dt.datetime.now()
st.metric('Current Time', now_local.strftime('%A, %b %d — %I:%M:%S %p'))

# Trigger check
triggered = False
for tmr in st.session_state.timers:
    # Parse timer time today
    hh, mm = map(int, tmr['time_hm'].split(':'))
    target = now_local.replace(hour=hh, minute=mm, second=0, microsecond=0)
    today_str = now_local.strftime('%Y-%m-%d')

    # Reset last_fired_date for repeating timers at day change
    if tmr['repeat'] and tmr['last_fired_date'] and tmr['last_fired_date'] != today_str:
        tmr['last_fired_date'] = None

    # Fire if time passed in this minute and not fired today
    if now_local >= target and now_local <= target + dt.timedelta(seconds=59):
        if tmr['last_fired_date'] != today_str:
            sound_bytes = st.session_state.sounds.get(tmr['sound_name'])
            if isinstance(sound_bytes, tuple):
                sound_bytes = sound_bytes[0]
            if sound_bytes:
                st.success(f"Time for: {tmr['label']}")
                audio_player_autoplay(sound_bytes)
                tmr['last_fired_date'] = today_str
                triggered = True

if not st.session_state.timers:
    st.info('No timers yet. Add one above!')

st.divider()
st.caption('Tip: Keep this tab open. Some browsers require one interaction (like pressing a play button) to enable autoplay audio.')

