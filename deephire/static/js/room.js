import { createTracker, baseline, isFacing } from './face.js';
import { speak, stopSpeaking, micMeter, startRecording } from './media.js';
import { saveTake } from './videos.js';

const session = JSON.parse(document.getElementById('session-data').textContent);
const $ = id => document.getElementById(id);
const room = $('room'), cam = $('cam');
const total = session.answers.length;

const MAX_ANSWER_S = 180;
const SAMPLE_MS = 200;        // face and level sampling: five times a second
const VOICE_FLOOR = 0.012;    // calibration knob: quietest RMS level counted as speech

let stream = null, meter = null, readFace = null, base = null, noise = 0;
let mode = 'check';           // check | speaking | reading | listening | saving | error | done
let index = 0, recording = null, startedAt = 0;
let counts = { samples: 0, face: 0, facing: 0 }, talkMs = 0, silenceMs = 0;
let kick = 0, needle = 0, lastFrame;

// ---------- small view helpers ----------
const fmt = s => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, '0')}`;
function setStatus(title, sub = '') { $('status').textContent = title; $('status-sub').textContent = sub; }
function showError(msg) { $('room-error').textContent = msg; $('room-error').hidden = !msg; }
function lamp(el, state, text) {
  el.dataset.state = state;
  if (text !== undefined) el.querySelector('span:last-child').textContent = text;
}
function controls({ primary = null, skip = false, end = true, busy = false } = {}) {
  $('done').hidden = !primary;
  if (primary) $('done').textContent = primary;
  $('done').disabled = busy;
  $('skip').hidden = !skip;
  $('skip').disabled = busy;
  $('end').hidden = !end;
  $('end').disabled = busy && mode === 'saving';
}
function markDone(stepId) { $(stepId).dataset.done = ''; }
function enable(stepId, buttonId) { $(stepId).removeAttribute('aria-disabled'); if (buttonId) $(buttonId).disabled = false; }

// ---------- one animation loop: the dial needle and the mic bars ----------
function animate() {
  const level = meter ? meter.level() : 0;
  let target;
  if (mode === 'speaking') { kick *= 0.9; target = 0.25 + kick * 0.55; }   // the interviewer's voice
  else target = Math.min(1, Math.max(0, (level - noise) * 9));              // your voice
  needle += (target - needle) * 0.18;                                        // roughly VU ballistics
  $('needle').style.transform = `rotate(${-62 + needle * 124}deg)`;

  const lit = Math.round(Math.min(1, level * 9) * 12);
  [...$('mic-bars').children].forEach((bar, i) => {
    bar.classList.toggle('on', i < lit);
    bar.classList.toggle('hi', i >= 8);
    bar.classList.toggle('top', i >= 11);
  });
  requestAnimationFrame(animate);
}

// ---------- sampling: face direction and talk/silence ----------
setInterval(() => {
  if (!stream) return;
  if (readFace) lastFrame = readFace(cam);
  const state = !readFace ? ['', 'Off'] : lastFrame === null ? ['warn', 'No face']
    : lastFrame === undefined ? ['', '…'] : !base ? ['on', 'Face found']
    : isFacing(lastFrame, base) ? ['on', 'On camera'] : ['warn', 'Looking away'];
  lamp($('camera-state'), state[0], state[1]);
  if (mode === 'check' && readFace) lamp($('chk-face'), lastFrame ? 'ok' : 'warn', lastFrame ? 'Face found' : 'Face tracking: no face yet');

  if (mode !== 'listening') return;
  if (readFace && base && lastFrame !== undefined) {
    counts.samples++;
    if (lastFrame) counts.face++;
    if (isFacing(lastFrame, base)) counts.facing++;
  }
  const talking = meter.level() > Math.max(VOICE_FLOOR, noise * 3);
  if (talking) { talkMs += SAMPLE_MS; silenceMs = 0; } else silenceMs += SAMPLE_MS;
  const elapsed = (performance.now() - startedAt) / 1000;
  $('talk-time').textContent = fmt(talkMs / 1000);
  $('silence').textContent = `${Math.floor(silenceMs / 1000)} s`;
  $('take-time').textContent = `${fmt(elapsed)} / ${fmt(MAX_ANSWER_S)}`;
  if (elapsed >= MAX_ANSWER_S) finishAnswer();
}, SAMPLE_MS);

// ---------- sound check ----------
$('consent').addEventListener('change', e => {
  if (e.target.checked) { markDone('step-consent'); enable('step-devices', 'devices'); }
  else { delete $('step-consent').dataset.done; $('devices').disabled = true; }
});

$('devices').addEventListener('click', async () => {
  $('devices').disabled = true;
  showError('');
  try {
    stream = await navigator.mediaDevices.getUserMedia({ video: { width: 1280, height: 720 }, audio: true });
  } catch {
    try { stream = await navigator.mediaDevices.getUserMedia({ audio: true }); }
    catch { showError('No microphone was available, or permission was refused. The interview needs a microphone; allow it in the address bar and try again.'); $('devices').disabled = false; return; }
  }
  const hasVideo = stream.getVideoTracks().length > 0;
  cam.srcObject = stream;
  cam.play().catch(() => {});                          // don't rely on autoplay alone
  $('cam-empty').hidden = hasVideo;
  if (!hasVideo) $('cam-empty').textContent = 'No camera: audio-only practice';
  const videoTrack = stream.getVideoTracks()[0];
  const cameraStopped = () => videoTrack?.readyState === 'ended';
  videoTrack?.addEventListener('ended', () => {        // unplugged, or taken by another app
    readFace = null; base = null;                      // a frozen frame must not count as "on camera"
    $('cam-empty').hidden = false;
    $('cam-empty').textContent = 'Camera stopped. Is another app using it?';
    lamp($('chk-cam'), 'error', 'Camera stopped');
  });
  meter = micMeter(stream);
  await meter.resume();
  $('checks').hidden = false;
  lamp($('chk-cam'), hasVideo ? 'ok' : 'error', hasVideo ? 'Camera' : 'No camera');
  lamp($('chk-mic'), 'ok', 'Microphone');
  markDone('step-devices');

  if (!hasVideo) { lamp($('chk-face'), 'error', 'Face tracking off'); readyToStart('Without a camera, the report leaves out the camera numbers.'); return; }
  lamp($('chk-face'), 'busy', 'Loading face tracking…');
  try {
    readFace = await createTracker();
    if (cameraStopped()) { readFace = null; readyToStart('The camera stopped, so the report leaves out the camera numbers.'); return; }
    enable('step-calibrate', 'calibrate');
  } catch (err) {
    console.error(err);
    lamp($('chk-face'), 'error', 'Face tracking unavailable');
    readyToStart('Face tracking could not load, so the report leaves out the camera numbers.');
  }
});

$('calibrate').addEventListener('click', async () => {
  $('calibrate').disabled = true;
  const frames = [], levels = [];
  const cue = $('cue');
  cue.hidden = false;
  for (let t = 0; t < 30; t++) {                       // 3 s at 10 per second
    cue.textContent = `Look into the lens · ${3 - Math.floor(t / 10)}`;
    frames.push(readFace(cam));
    levels.push(meter.level());
    await new Promise(r => setTimeout(r, 100));
  }
  cue.hidden = true;
  levels.sort((a, b) => a - b);
  noise = levels[Math.floor(levels.length / 2)];
  base = baseline(frames);
  if (!base) {
    $('calibrate').disabled = false;
    showError("Couldn't find your face in those three seconds. Put the light in front of you and try again, or start without camera numbers.");
    readyToStart();
    return;
  }
  showError('');
  markDone('step-calibrate');
  readyToStart();
});

function readyToStart(note) {
  enable('step-start', 'start');
  if (note) $('step-start').querySelector('p').textContent = note;
}

$('start').addEventListener('click', () => {
  $('steps').hidden = true;
  $('live').hidden = false;
  room.dataset.phase = 'live';
  askQuestion(0);
});

// ---------- the interview ----------
async function askQuestion(i) {
  index = i;
  const q = session.answers[i].question;
  $('take-no').textContent = `Question ${i + 1} of ${total}`;
  $('take-time').textContent = `0:00 / ${fmt(MAX_ANSWER_S)}`;
  $('question').textContent = q;
  $('question-hint').textContent = /\b(write|implement|code)\b|function/i.test(q)
    ? 'Coding question: talk through your approach — the data structures, the steps, and the complexity.' : '';
  showError('');
  mode = 'speaking';
  setStatus('Interviewer speaking', 'The question is on screen too.');
  controls({ primary: 'Answer now', skip: true });
  const spoke = await speak(q, () => { kick = 1; });
  if (mode !== 'speaking' || index !== i) return;      // skipped or ended while speaking
  if (!spoke) {
    mode = 'reading';
    setStatus('Read the question', 'No local voice was found on this computer. Start when you are ready.');
    controls({ primary: 'Start answering', skip: true });
    return;
  }
  beginAnswer();
}

function beginAnswer() {
  stopSpeaking();
  mode = 'listening';
  counts = { samples: 0, face: 0, facing: 0 };
  talkMs = 0; silenceMs = 0;
  startedAt = performance.now();
  recording = startRecording(stream);
  $('dial-text').textContent = 'Your mic';
  setStatus('Your answer', 'Recording to this browser. Pausing to think is fine.');
  controls({ primary: 'Done answering', skip: true });
}

async function finishAnswer(thenEnd = false) {
  if (mode !== 'listening') return;
  mode = 'saving';
  $('dial-text').textContent = 'Talkback';
  setStatus('Saving take', 'Transcribing on this computer…');
  controls({ primary: 'Done answering', skip: true, busy: true });
  const { video, voice, duration } = await recording.stop();
  recording = null;
  try { await saveTake(session.session_id, index, video); }
  catch (err) { console.warn('replay not saved', err); }     // storage blocked or full: keep going

  const form = new FormData();
  form.append('session_id', session.session_id);
  form.append('index', index);
  form.append('duration', duration.toFixed(2));
  form.append('face', JSON.stringify(base ? counts : { samples: 0 }));
  form.append('audio', voice, 'answer.webm');
  try {
    const r = await fetch('/api/answer', { method: 'POST', body: form });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(data.error || `The server answered ${r.status}.`);
  } catch (err) {
    mode = 'error';
    setStatus('That take was not saved', 'You can answer again or move on.');
    showError(`${err.message} Is the DeepHire server still running?`);
    controls({ primary: 'Answer again', skip: true });
    return;
  }
  thenEnd ? finish() : next();
}

function next() { index + 1 < total ? askQuestion(index + 1) : finish(); }

function finish() {
  mode = 'done';
  stopSpeaking();
  stream?.getTracks().forEach(t => t.stop());
  location.href = `/report?session=${session.session_id}`;
}

$('done').addEventListener('click', () => {
  if (mode === 'speaking' || mode === 'reading' || mode === 'error') beginAnswer();
  else if (mode === 'listening') finishAnswer();
});

$('skip').addEventListener('click', async () => {
  if (mode === 'listening') { mode = 'skipping'; await recording.stop(); recording = null; }
  stopSpeaking();
  next();
});

$('end').addEventListener('click', () => {
  if (mode === 'listening') finishAnswer(true);       // keep the answer in progress
  else finish();
});

$('toggle-levels').addEventListener('click', e => {
  const hide = room.dataset.levels !== 'hidden';
  room.dataset.levels = hide ? 'hidden' : '';
  e.currentTarget.textContent = hide ? 'Show levels' : 'Hide levels';
  e.currentTarget.setAttribute('aria-pressed', String(hide));
  try { localStorage.setItem('deephire-levels', hide ? 'hidden' : ''); } catch {}
});
// Phones start with the levels hidden so the pinned bar is just the controls; the toggle brings them back.
let savedLevels = null;
try { savedLevels = localStorage.getItem('deephire-levels'); } catch {}
if (savedLevels === 'hidden' || (savedLevels === null && matchMedia('(max-width: 640px)').matches)) $('toggle-levels').click();

addEventListener('beforeunload', e => { if (mode === 'listening' || mode === 'saving') e.preventDefault(); });

controls({ end: false });
requestAnimationFrame(animate);
