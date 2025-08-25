import streamlit as st
import datetime as dt
import base64, io, wave, time, os, requests, json
import numpy as np
from zoneinfo import ZoneInfo

# ─────────────────────────────────────────────────────────────
# App config
# ─────────────────────────────────────────────────────────────
st.set_page_config(page_title="Meditation Chimes", page_icon="🧘", layout="centered")
TZ = ZoneInfo("America/New_York")
SR = 44100  # audio sample rate

# ─────────────────────────────────────────────────────────────
# Audio synthesis
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
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SR)
        wf.writeframes((y * 32767).astype("<i2").tobytes())
    return buf.getvalue()

def builtin_sounds():
    bell = synth_tone([(880,0.9),(1760,0.5),(2637,0.25)], duration=0.6, decay=6.0)
    return {
        "Soft Bell": (synth_tone([(660,0.6),(990,0.4),(1320,0.2)], 2.2, 2.0), "audio/wav"),
        "Singing Bowl": (synth_tone([(196,0.8),(392,0.35),(294,0.25)], 3.0, 1.1), "audio/wav"),
        "Wood Block": (synth_tone([(880,1.0)], 0.35, 6.5), "audio/wav"),
        "School Bell (synthetic)": (bell, "audio/wav"),
    }

# ─────────────────────────────────────────────────────────────
# Remote sound helper
# ─────────────────────────────────────────────────────────────
@st.cache_data(ttl=86400, show_spinner=False)
def fetch_remote_bytes(url: str):
    try:
        r = requests.get(url, timeout=10)
        if r.status_code == 200 and r.content:
            return r.content
    except Exception:
        pass
    return None

def to_raw_github_url(blob_url: str) -> str:
    if "github.com/" in blob_url and "/blob/" in blob_url:
        return blob_url.replace("github.com/", "raw.githubusercontent.com/").replace("/blob/", "/")
    return blob_url

# ─────────────────────────────────────────────────────────────
# Session state
# ─────────────────────────────────────────────────────────────
if "sounds" not in st.session_state:
    lib = {}
    lib.update(builtin_sounds())
    # Try your GitHub school bell
    gh_blob = "https://github.com/vinayakagude/Alarm/blob/main/hailuoto-school-bell-recording-106632.mp3"
    raw = to_raw_github_url(gh_blob)
    data = fetch_remote_bytes(raw)
    if data:
        lib["School Bell"] = (data, "audio/mpeg")
    st.session_state.sounds = lib

if "timers" not in st.session_state:
    st.session_state.timers = []

# ─────────────────────────────────────────────────────────────
# UI
# ─────────────────────────────────────────────────────────────
st.title("🧘 Meditation Chimes — Day Planner")
st.caption("US/Eastern time. Every-minute schedules with chimes that play for N seconds.")

# Live clock (client-side, always smooth)
clock_html = """
<div id="et-clock" style="font-size:1.1rem;margin:.25rem 0 1rem 0;font-family: ui-monospace, monospace;"></div>
<script>
function pad(n){return n<10?('0'+n):n}
function tick(){
  try{
    const now=new Date();
    const et = new Date(now.toLocaleString('en-US',{timeZone:'America/New_York'}));
    const wd  = et.toLocaleDateString('en-US',{weekday:'long'});
    const mon = et.toLocaleDateString('en-US',{month:'short'});
    const d   = et.getDate();
    const h12 = ((et.getHours()+11)%12)+1;
    const mm  = pad(et.getMinutes());
    const ss  = pad(et.getSeconds());
    const ap  = et.getHours()>=12?'PM':'AM';
    document.getElementById('et-clock').textContent =
      '[' + wd + '] ' + mon + ' ' + d + ' — ' + pad(h12) + ':' + mm + ':' + ss + ' ' + ap + ' ET';
  }catch(e){}
}
tick(); setInterval(tick, 1000);
</script>
"""
st.components.v1.html(clock_html, height=34)

# Autoplay priming (best-effort; still falls back to first click if the browser needs a gesture)
silent = synth_tone([(440, 0.0)], duration=0.1)
silent_b64 = base64.b64encode(silent).decode()
st.components.v1.html(
    "<audio id='priming' autoplay muted playsinline style='display:none'>"
    "<source src='data:audio/wav;base64," + silent_b64 + "'>"
    "</audio>",
    height=0
)

with st.sidebar:
    st.header("Preview & Settings")
    name = st.selectbox("Preview a sound", list(st.session_state.sounds.keys()))
    secs = st.slider("Preview length (sec)", 1, 20, 4)
    if st.button("▶️ Preview"):
        data, mime = st.session_state.sounds[name]
        b64 = base64.b64encode(data).decode()
        st.components.v1.html(
            "<audio autoplay controls>"
            "<source src='data:" + mime + ";base64," + b64 + "'>"
            "</audio>",
            height=48
        )

    st.divider()
    st.subheader("Add remote sound (GitHub blob or direct URL)")
    default_url = "https://github.com/vinayakagude/Alarm/blob/main/hailuoto-school-bell-recording-106632.mp3"
    u = st.text_input("URL", default_url)
    if st.button("Add Remote Sound") and u.strip():
        raw = to_raw_github_url(u.strip())
        d = fetch_remote_bytes(raw)
        if d:
            st.session_state.sounds["Remote: " + os.path.basename(raw)] = (d, "audio/mpeg")
            st.success("Remote sound added.")
        else:
            st.warning("Could not fetch that URL.")

with st.form("add_block"):
    st.subheader("Create a Chime Schedule")
    label = st.text_input("Label", "Meditation")
    c1, c2, c3 = st.columns(3)
    start_time = c1.time_input("Start time", dt.time(9,0), step=60)
    end_time   = c2.time_input("End time",   dt.time(17,0), step=60)
    interval_min = c3.number_input("Repeat every (min)", 1, 240, 1)
    c4, c5 = st.columns(2)
    sound_name   = c4.selectbox("Chime sound", list(st.session_state.sounds.keys()))
    play_seconds = c5.number_input("Each alarm plays (sec)", 1, 300, 8)

    submitted = st.form_submit_button("Add Schedule")
    if submitted:
        if end_time <= start_time:
            st.error("End time must be after start time.")
        else:
            st.session_state.timers.append({
                "id": int(time.time()*1000),
                "label": label.strip(),
                "start": start_time.strftime("%H:%M"),  # "HH:MM"
                "end":   end_time.strftime("%H:%M"),    # "HH:MM"
                "interval_min": int(interval_min),
                "sound": sound_name,
                "play_seconds": int(play_seconds),
            })
            st.success("Schedule added!")

st.subheader("Today's Schedules (ET)")
remove = []
for t in st.session_state.timers:
    st.write(f"**{t['label']}** • {t['start']} → {t['end']} • every {t['interval_min']} min • {t['play_seconds']}s • {t['sound']}")
    if st.button("✖️ Delete", key=f"del_{t['id']}"):
        remove.append(t["id"])
if remove:
    st.session_state.timers = [x for x in st.session_state.timers if x["id"] not in remove]
    st.success("Removed schedule(s).")

# ─────────────────────────────────────────────────────────────
# Client-side scheduler (reliable repeat, no server reruns)
# ─────────────────────────────────────────────────────────────
# Build schedules payload with data URLs
schedules = []
for t in st.session_state.timers:
    data, mime = st.session_state.sounds[t["sound"]]
    b64 = base64.b64encode(data).decode()
    schedules.append({
        "id": t["id"],
        "label": t["label"],
        "start": t["start"],          # "HH:MM"
        "end":   t["end"],            # "HH:MM"
        "interval_min": t["interval_min"],
        "play_seconds": t["play_seconds"],
        "data_url": "data:" + mime + ";base64," + b64,
    })
schedules_json = json.dumps(schedules)

html = (
  "<div id='alarm-log' style='font-size:.9rem;color:#666;margin:6px 0 0 0;'></div>"
  "<script id='sched-data' type='application/json'>" + schedules_json + "</script>"
  "<script>(function(){"
  "  var dataEl = document.getElementById('sched-data');"
  "  var schedules = JSON.parse(dataEl.textContent);"
  "  var fired = {}; // { 'YYYY-MM-DD': { id: { 'HH:MM': true } } }"

  "  function etNow(){ var now=new Date();"
  "    return new Date(now.toLocaleString('en-US',{timeZone:'America/New_York'})); }"

  "  function hm(d){ var hh=('0'+d.getHours()).slice(-2);"
  "    var mm=('0'+d.getMinutes()).slice(-2); return hh+':'+mm; }"

  "  function minsBetween(startHM, currentHM){"
  "    var sh=parseInt(startHM.slice(0,2),10), sm=parseInt(startHM.slice(3),10);"
  "    var ch=parseInt(currentHM.slice(0,2),10), cm=parseInt(currentHM.slice(3),10);"
  "    return (ch*60+cm)-(sh*60+sm); }"

  "  function playForSeconds(url, secs){"
  "    var a=new Audio(); a.src=url; a.loop=true; a.preload='auto'; a.crossOrigin='anonymous';"
  "    // Best-effort autoplay; if blocked, first click anywhere will start it"
  "    function start(){ try{ a.play(); }catch(e){} }"
  "    start();"
  "    document.addEventListener('click', function once(){ start(); document.removeEventListener('click', once); }, {once:true});"
  "    setTimeout(function(){ try{ a.loop=false; a.pause(); a.src=''; }catch(e){} }, Math.max(1,secs)*1000);"
  "  }"

  "  function tick(){"
  "    var now=etNow();"
  "    var ymd = now.getFullYear()+'-'+('0'+(now.getMonth()+1)).slice(-2)+'-'+('0'+now.getDate()).slice(-2);"
  "    var curHM = hm(now);"
  "    if(!fired[ymd]) fired[ymd] = {};"
  "    for(var i=0;i<schedules.length;i++){"
  "      var s=schedules[i];"
  "      if(!fired[ymd][s.id]) fired[ymd][s.id] = {};"
  "      var mFromStart = minsBetween(s.start, curHM);"
  "      var mFromEnd   = minsBetween(s.start, s.end);"
  "      if(mFromStart>=0 && mFromStart<=mFromEnd){"
  "        if(mFromStart % s.interval_min === 0){"
  "          if(!fired[ymd][s.id][curHM]){"
  "            playForSeconds(s.data_url, s.play_seconds);"
  "            fired[ymd][s.id][curHM] = true;"
  "            var log=document.getElementById('alarm-log');"
  "            if(log){ var p=document.createElement('div'); p.textContent='['+curHM+'] '+s.label; log.appendChild(p); }"
  "          }"
  "        }"
  "      }"
  "    }"
  "  }"

  "  setInterval(tick, 500); tick();"
  "})();</script>"
)
st.components.v1.html(html, height=0)
