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

st.set_page_config(page_title='Meditation Chimes', page_icon='🧘', layout='centered')
TZ = ZoneInfo('America/New_York')
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
    bell = synth_tone([(880,0.9),(1760,0.5),(2637,0.25)],duration=0.6,decay=6.0)
    return {
        "Soft Bell": (synth_tone([(660,0.6),(990,0.4),(1320,0.2)],2.2,2.0),'audio/wav'),
        "Singing Bowl": (synth_tone([(196,0.8),(392,0.35),(294,0.25)],3.0,1.1),'audio/wav'),
        "Wood Block": (synth_tone([(880,1.0)],0.35,6.5),'audio/wav'),
        "School Bell (synthetic)": (bell,'audio/wav')
    }

def generate_gongs_and_bowls(n=100, seed=7):
    rng=np.random.default_rng(seed)
    sounds={}
    categories=[("Deep Gong",90,2.5),("Bronze Gong",140,2.2),("Temple Gong",220,2.0),("Singing Bowl",196,1.3),("Wind Chime",660,3.5)]
    for i in range(n):
        name,base,decay=categories[i%len(categories)]
        parts=[]
        for k in range(1,rng.integers(3,6)+1):
            det=rng.normal(0,0.015)
            amp=max(0.15,1.2/(k+rng.random()))
            parts.append(((base*k)*(1+det),amp))
        wav=synth_tone(parts,2.0+float(rng.random()*1.5),decay)
        sounds[f"{name} #{i+1}"]=(wav,'audio/wav')
    return sounds

@st.cache_data(ttl=86400)
def fetch_remote_bytes(url):
    try:
        r=requests.get(url,timeout=10)
        if r.status_code==200 and r.content:
            return r.content
    except: return None
    return None

def to_raw_github_url(blob_url:str)->str:
    if 'github.com/' in blob_url and '/blob/' in blob_url:
        return blob_url.replace('github.com/','raw.githubusercontent.com/').replace('/blob/','/')
    return blob_url

def audio_player_autoplay(audio_bytes, mime='audio/wav', key='aplayer', repeat_seconds=1):
    """Repeat within the window by *re‑striking* the audio every 2s.
    This guarantees multiple hits even if the file is long.
    """
    b64 = base64.b64encode(audio_bytes).decode()
    dur_ms = 1000 * max(1, int(repeat_seconds))
    html = """
<div style='display:flex;align-items:center;gap:.5rem'>
  <audio id='""" + key + """' preload='auto'>
    <source src='data:""" + mime + """;base64,""" + b64 + """'>
  </audio>
  <button id='btn_""" + key + """' style='padding:2px 8px;border-radius:6px;font-size:12px'>Enable sound</button>
</div>
<script>
(function(){
  var a=document.getElementById('""" + key + """');
  var btn=document.getElementById('btn_""" + key + """');
  var endTime=Date.now()+""" + str(dur_ms) + """;
  var period=2000; // strike every 2s
  function strike(){
    try{ a.pause(); a.currentTime=0; a.play().catch(function(){}); }catch(e){}
  }
  function start(){ strike(); }
  // start immediately
  start();
  // gesture fallbacks
  ['click','pointerdown','keydown','touchstart'].forEach(function(ev){ document.addEventListener(ev, start, { once:true }); });
  if(btn) btn.addEventListener('click', start, { once:true });
  // repeat strikes during window
  var iv=setInterval(function(){
    if(Date.now() < endTime){ strike(); }
    else { try{ clearInterval(iv); a.pause(); a.currentTime=0; }catch(e){} }
  }, period);
})();
</script>
"""
    st.components.v1.html(html, height=60)

if 'sounds' not in st.session_state:
    lib={}
    lib.update(builtin_sounds_base())
    lib.update(generate_gongs_and_bowls(100))
    local='/mnt/data/hailuoto-school-bell-recording-106632.mp3'
    if os.path.exists(local):
        try:
            with open(local,'rb') as f:
                lib['School Bell']=(f.read(),'audio/mpeg')
        except: pass
    url=to_raw_github_url('https://github.com/vinayakagude/Alarm/blob/main/hailuoto-school-bell-recording-106632.mp3')
    c=fetch_remote_bytes(url)
    if c: lib['School Bell']=(c,'audio/mpeg')
    st.session_state.sounds=lib

if 'timers' not in st.session_state: st.session_state.timers=[]
if 'running' not in st.session_state: st.session_state.running=True

st.title('🧘 Meditation Chimes — Day Planner')
st.caption('US/Eastern time. Continuous 1‑minute interval. Clock updates live.')

# Client-side active clock
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
tick();setInterval(tick,1000);
</script>
"""
st.components.v1.html(clock_html,height=36)

with st.sidebar:
    st.header('Preview & Settings')
    st.toggle('Running',value=st.session_state.running,key='running')
    preview=st.selectbox('Preview a sound',list(st.session_state.sounds.keys()))
    secs=st.slider('Preview length (sec)',1,20,4)
    if st.button('▶️ Preview'):
        d,m=st.session_state.sounds[preview] if isinstance(st.session_state.sounds[preview],tuple) else (st.session_state.sounds[preview],'audio/wav')
        audio_player_autoplay(d,m,key='preview',repeat_seconds=secs)

    st.divider()
    st.subheader('Add remote sound via URL')
    default_url='https://github.com/vinayakagude/Alarm/blob/main/hailuoto-school-bell-recording-106632.mp3'
    u=st.text_input('Paste URL',default_url)
    if st.button('Add Remote Sound') and u.strip():
        raw=to_raw_github_url(u.strip())
        d=fetch_remote_bytes(raw)
        if d:
            name=os.path.basename(raw)
            st.session_state.sounds[f'Remote: {name}']=(d,'audio/mpeg')
            st.success(f'Added remote sound: {name}')
        else:
            st.warning('Could not fetch URL')

with st.form('add_block'):
    st.subheader('Create a Chime Schedule')
    label=st.text_input('Label','Meditation')
    c1,c2,c3=st.columns(3)
    start_time=c1.time_input('Start time',dt.time(9,0),step=60)
    end_time=c2.time_input('End time',dt.time(17,0),step=60)
    interval_min=c3.number_input('Repeat every (min)',1,1,1)
    c4,c5=st.columns(2)
    sound_name=c4.selectbox('Chime sound',list(st.session_state.sounds.keys()))
    play_seconds=c5.number_input('Each alarm plays (sec)',1,300,5)
    repeat_daily=st.checkbox('Repeat daily',True)
    submitted=st.form_submit_button('Add Schedule')
    if submitted:
        if end_time<=start_time:
            st.error('End time must be after start time.')
        else:
            st.session_state.timers.append({
                'id':int(time.time()*1000),
                'label':label.strip(),
                'start':start_time.strftime('%H:%M:%S'),
                'end':end_time.strftime('%H:%M:%S'),
                'interval_min':int(interval_min),
                'sound':sound_name,
                'play_seconds':int(play_seconds),
                'repeat_daily':repeat_daily,
                'last_day':None,
                'fired':[],
            })
            st.success("Schedule added!")

st.subheader("Today's Schedules")
remove=[]
for t in st.session_state.timers:
    st.write(f"**{t['label']}** • {t['start']} → {t['end']} • every {t['interval_min']} min • {t['play_seconds']}s • {t['sound']}")
    if st.button('✖️ Delete',key=f"del_{t['id']}"): remove.append(t['id'])
if remove:
    st.session_state.timers=[x for x in st.session_state.timers if x['id'] not in remove]
    st.success('Removed schedule(s).')

# Scheduler loop
now=dt.datetime.now(TZ)
today=now.strftime('%Y-%m-%d')
for t in st.session_state.timers:
    if t['last_day']!=today:
        t['fired']=[];t['last_day']=today
    parts_s=list(map(int,t['start'].split(':')))
    parts_e=list(map(int,t['end'].split(':')))
    while len(parts_s)<3: parts_s.append(0)
    while len(parts_e)<3: parts_e.append(0)
    hh_s,mm_s,ss_s=parts_s
    hh_e,mm_e,ss_e=parts_e
    sdt=now.replace(hour=hh_s,minute=mm_s,second=ss_s,microsecond=0)
    edt=now.replace(hour=hh_e,minute=mm_e,second=ss_e if ss_e>0 else 59,microsecond=0)
    if sdt<=now<=edt:
        elapsed=int((now-sdt).total_seconds()//60)
        if elapsed%t['interval_min']==0:
            hm=now.strftime('%H:%M')
            if hm not in t['fired']:
                d,m=st.session_state.sounds[t['sound']] if isinstance(st.session_state.sounds[t['sound']],tuple) else (st.session_state.sounds[t['sound']],'audio/wav')
                st.success(f"Time for: {t['label']} ({hm})")
                audio_player_autoplay(d,m,key=f"play_{t['id']}_{hm}",repeat_seconds=t['play_seconds'])
                t['fired'].append(hm)

# Ensure the scheduler runs frequently enough to catch minute boundaries
if st.session_state.running:
    st.components.v1.html(
        """
        <script>
          setTimeout(function(){
            const url = new URL(window.location.href);
            url.searchParams.set('ts', Date.now());
            window.location.replace(url.toString());
          }, 1000);
        </script>
        """,
        height=0,
    )
