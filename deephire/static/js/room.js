import { createTracker, baseline, isFacing } from './face.js';
import { speak, stopSpeaking, micMeter, startRecording, voiceLevel, prefetchSpeech } from './media.js';
import { saveTake } from './videos.js';

const session = JSON.parse(document.getElementById('session-data').textContent);
const WRAP_UP = JSON.parse(document.getElementById('wrap-up').textContent);   // the interviewer's cut-in lines
const $ = id => document.getElementById(id);
const room = $('room'), cam = $('cam');
const total = session.answers.length;

const MAX_ANSWER_S = 180;
const SAMPLE_MS = 200;        // face and level sampling: five times a second
const VOICE_FLOOR = 0.012;    // calibration knob: quietest RMS level counted as speech

let stream = null, meter = null, readFace = null, base = null, noise = 0;
let mode = 'check';           // check | speaking | reading | listening | saving | error | done
let index = 0, recording = null, startedAt = 0, part = 'main';   // part: main | follow_up
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
  $('skip').textContent = part === 'follow_up' ? 'Skip follow-up' : 'Skip question';
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
  if (mode === 'speaking' || mode === 'interrupting') {                     // the interviewer's voice
    kick *= 0.9;
    const v = voiceLevel();
    target = v ? Math.min(1, 0.15 + v * 5) : 0.25 + kick * 0.55;
  }
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
    $('calibrate').disabled = true;
    $('setup-check').disabled = true;
    if (mode === 'check') readyToStart('The camera stopped, so the report leaves out the camera numbers.');
  });
  meter = micMeter(stream);
  await meter.resume();
  $('checks').hidden = false;
  lamp($('chk-cam'), hasVideo ? 'ok' : 'error', hasVideo ? 'Camera' : 'No camera');
  lamp($('chk-mic'), 'ok', 'Microphone');
  markDone('step-devices');
  if (hasVideo) enable('step-setup', 'setup-check');

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
  for (let t = 0; t < 30 && readFace; t++) {           // 3 s at 10 per second; stops if the camera does
    cue.textContent = `Look into the lens · ${3 - Math.floor(t / 10)}`;
    frames.push(readFace(cam));
    levels.push(meter.level());
    await new Promise(r => setTimeout(r, 100));
  }
  cue.hidden = true;
  levels.sort((a, b) => a - b);
  noise = levels[Math.floor(levels.length / 2)];
  base = readFace ? baseline(frames) : null;
  if (!readFace) return;                               // the camera stopped mid-calibration; already handled
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

const el = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; };
const busy = (tag, text) => {   // the system's in-progress signal: an amber lamp
  const e = el(tag, 'take-state'), lampEl = el('span', 'lamp');
  lampEl.dataset.state = 'busy';
  lampEl.append(el('span', 'led'));
  e.append(lampEl, text);
  return e;
};

// ---------- optional camera-setup check: one frame to the local vision model ----------
$('setup-check').addEventListener('click', async () => {
  const button = $('setup-check'), list = $('setup-tips');
  button.disabled = true;
  list.hidden = false;
  list.replaceChildren(busy('li', 'Looking at your setup… the first check can take a minute while the model loads.'));
  list.firstChild.classList.add('pending');
  const canvas = document.createElement('canvas');
  canvas.width = cam.videoWidth;
  canvas.height = cam.videoHeight;
  canvas.getContext('2d').drawImage(cam, 0, 0);
  const frame = await new Promise(r => canvas.toBlob(r, 'image/jpeg', 0.85));
  const form = new FormData();
  form.append('frame', frame, 'frame.jpg');
  try {
    const r = await fetch('/api/camera-check', { method: 'POST', body: form });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(data.error || `The server answered ${r.status}.`);
    list.replaceChildren(...data.tips.map(t => el('li', '', t)));
    markDone('step-setup');
  } catch (err) {
    list.replaceChildren(el('li', 'error', err.message));
  }
  button.disabled = false;
  button.lastChild.textContent = 'Check again';
});

$('start').addEventListener('click', () => {
  fetch('/api/warmup', { method: 'POST' }).catch(() => {});  // reload the grading model if the setup check swapped it out
  $('steps').hidden = true;
  $('live').hidden = false;
  room.dataset.phase = 'live';
  askQuestion(0);
});

// ---------- the interview ----------
const takes = {};                      // index -> { main: delivery, follow_up: delivery }
const takeKey = () => (part === 'main' ? index : `${index}f`);

function showQuestion(text, hint) {
  $('quick-take').hidden = true;
  $('live').hidden = false;
  $('take-time').textContent = `0:00 / ${fmt(MAX_ANSWER_S)}`;
  $('question').textContent = text;
  $('question').classList.toggle('long', text.split(' ').length > 45);
  $('question-hint').textContent = hint;
  $('live-caption').hidden = true;
  $('live-caption').textContent = '';
  showError('');
}

async function say(text, sub) {
  const mine = `${index}${part}`;
  mode = 'speaking';
  setStatus('Interviewer speaking', sub);
  controls({ primary: 'Answer now', skip: true });
  const spoke = await speak(text, () => { kick = 1; });
  if (mode !== 'speaking' || `${index}${part}` !== mine) return;   // skipped or ended while speaking
  if (!spoke) {
    mode = 'reading';
    setStatus('Read the question', 'No local voice was found on this computer. Start when you are ready.');
    controls({ primary: 'Start answering', skip: true });
    return;
  }
  beginAnswer();
}

function askQuestion(i) {
  index = i;
  part = 'main';
  const q = session.answers[i].question;
  $('take-no').textContent = `Question ${i + 1} of ${total}`;
  if (i + 1 < total) prefetchSpeech(session.answers[i + 1].question);   // voiced while you answer this one
  showQuestion(q, /\b(write|implement|code)\b|function/i.test(q)
    ? 'Coding question: talk through your approach — the data structures, the steps, and the complexity.' : '');
  say(q, 'The question is on screen too.');
}

function askFollowUp(q) {
  part = 'follow_up';
  $('take-no').textContent = `Question ${index + 1} of ${total} · Follow-up`;
  showQuestion(q, `You were asked: ${session.answers[index].question}`);
  say(q, 'A follow-up about your answer.');
}

let live = null, liveChain = Promise.resolve(), liveOk = false;

// Each 1.5 s chunk goes to the local server in order; the reply carries the caption so far and
// whether the answer is running long or going in circles.
function sendChunk(pcm, seq, i, p) {
  liveChain = liveChain.then(async () => {
    try {
      const r = await fetch(`/api/stream/${session.session_id}/${i}/${p}?seq=${seq}`, {
        method: 'POST', headers: { 'Content-Type': 'application/octet-stream' }, body: pcm.buffer,
      });
      if (!r.ok) throw new Error(r.status);
      const data = await r.json();
      if (mode !== 'listening' || index !== i || part !== p) return;
      if (data.text) {
        $('live-caption').hidden = false;
        $('live-caption').textContent = data.text.length > 160 ? `…${data.text.slice(-160)}` : data.text;
      }
      if (data.ramble && session.interruptions) interrupt(data.ramble);
    } catch {
      liveOk = false;   // the full recording is transcribed instead
    }
  });
}

async function beginAnswer() {
  stopSpeaking();
  mode = 'listening';
  counts = { samples: 0, face: 0, facing: 0 };
  talkMs = 0; silenceMs = 0;
  startedAt = performance.now();
  recording = startRecording(stream);
  $('dial-text').textContent = 'Your mic';
  setStatus('Your answer', 'Recording to this browser. Pausing to think is fine.');
  controls({ primary: 'Done answering', skip: true });
  const i = index, p = part;
  liveChain = Promise.resolve();
  liveOk = true;
  try {
    live = await meter.liveChunks((pcm, seq) => sendChunk(pcm, seq, i, p));
  } catch (err) {
    console.warn('live transcription unavailable', err);
    live = null;
    liveOk = false;
  }
}

// The interviewer cuts in: speak the wrap-up line straight away while the answer is saved.
async function interrupt(reason) {
  if (mode !== 'listening') return;
  const wasFollowUp = part === 'follow_up';
  const line = wasFollowUp ? "Thanks, that's enough on this one. Let's move on." : WRAP_UP[reason];
  const saving = submitTake(reason);                   // stops recording; runs while the interviewer talks
  mode = 'interrupting';
  setStatus('Interviewer', reason === 'long' ? 'Cutting in: the answer is running long.' : 'Cutting in: the answer is going in circles.');
  controls({ primary: null, skip: false });
  await speak(line, () => { kick = 1; });
  const data = await saving;
  if (!data) return;
  if (wasFollowUp) return afterQuestion();
  part = 'follow_up';
  $('take-no').textContent = `Question ${index + 1} of ${total} · Follow-up`;
  showQuestion(line, `You were asked: ${session.answers[index].question}`);
  beginAnswer();
}

async function finishAnswer(thenEnd = false) {
  if (mode !== 'listening') return;
  const thinking = part === 'main' && session.follow_ups && !thenEnd;
  const data = await submitTake(null, thinking);
  if (!data) return;
  if (thenEnd) return finish();
  if (part === 'main' && data.follow_up) return askFollowUp(data.follow_up.question);
  afterQuestion();
}

// Stops recording, saves the replay locally, and posts the take. Returns the server's reply, or null
// after putting the room into its "answer again" state.
async function submitTake(interrupted, thinking = false) {
  mode = 'saving';
  $('dial-text').textContent = 'Talkback';
  if (!interrupted) {
    setStatus(thinking ? 'Thinking' : 'Saving take',
      thinking ? 'Transcribing. A follow-up may come next.' : 'Transcribing on this computer…');
    controls({ primary: 'Done answering', skip: true, busy: true });
  }
  live?.stop();                                        // sends the last partial chunk
  live = null;
  let video, voice, duration;
  try {
    ({ video, voice, duration } = await recording.stop());
  } catch (err) {
    console.error(err);
    mode = 'error';
    setStatus('That take was not saved', 'The recorder stopped unexpectedly. You can answer again or move on.');
    controls({ primary: 'Answer again', skip: true });
    return null;
  } finally {
    recording = null;
  }
  // The replay is a nicety: a blocked, full or slow browser store must not hold up the interview.
  await Promise.race([saveTake(session.session_id, takeKey(), video), new Promise(r => setTimeout(r, 5000))])
    .catch(err => console.warn('replay not saved', err));

  const form = new FormData();
  form.append('session_id', session.session_id);
  form.append('index', index);
  form.append('part', part);
  form.append('duration', duration.toFixed(2));
  form.append('face', JSON.stringify(base ? counts : { samples: 0 }));
  form.append('audio', voice, 'answer.webm');          // a fallback if live transcription missed anything
  await liveChain;                                     // every chunk is on the server first
  form.append('streamed', liveOk ? '1' : '0');
  if (interrupted) form.append('interrupted', interrupted);
  let data;
  try {
    const r = await fetch('/api/answer', { method: 'POST', body: form, signal: AbortSignal.timeout(180000) });
    data = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(data.error || `The server answered ${r.status}.`);
  } catch (err) {
    mode = 'error';
    setStatus('That take was not saved', 'You can answer again or move on.');
    showError(`${err.name === 'TimeoutError' ? 'The server took too long.' : err.message} Is the DeepHire server still running?`);
    controls({ primary: 'Answer again', skip: true });
    return null;
  }
  takes[index] = { ...takes[index], [part]: data.delivery };
  return data;
}

function afterQuestion() { session.mode === 'practice' && takes[index] ? quickTake(index) : next(); }
function next() { index + 1 < total ? askQuestion(index + 1) : finish(); }

async function finish() {
  mode = 'done';
  stopSpeaking();
  stream?.getTracks().forEach(t => t.stop());
  await fetch(`/api/finish/${session.session_id}`, { method: 'POST' }).catch(() => {});  // grade any open exchange
  location.href = `/report?session=${session.session_id}`;
}

// ---------- practice mode: a quick take between questions ----------
function quickTake(i) {
  mode = 'quick-take';
  $('live').hidden = true;
  $('quick-take').hidden = false;
  $('qt-title').textContent = `Quick take · Question ${i + 1} of ${total}`;
  setStatus('Quick take', 'Have a look, then move on when you are ready.');
  controls({ primary: i + 1 < total ? 'Next question' : 'See the track sheet' });

  const item = (label, value, note) => {
    const d = el('div');
    const dd = el('dd', '', value ?? '—');
    if (note) dd.append(el('small', '', ` ${note}`));
    d.append(el('dt', 'legend', label), dd);
    return d;
  };
  const blocks = [];
  for (const key of ['main', 'follow_up']) {
    const d = takes[i][key];
    if (!d) continue;
    const dl = el('dl', 'delivery');
    dl.append(item('Pace', d.wpm, d.wpm ? 'wpm (guide 120–160)' : 'too short to measure'),
      item('Pauses', d.pause_count, d.pause_count ? `longest ${d.longest_pause_s} s` : ''),
      item('Fillers', d.filler_count, d.fillers_per_min != null ? `${d.fillers_per_min}/min` : ''),
      item('On camera', d.camera_pct != null ? `${d.camera_pct}%` : null, d.camera_pct == null ? 'no camera data' : ''));
    if (key === 'follow_up') {   // the legend belongs to its list, not floating between the two
      const group = el('div', 'qt-group');
      group.append(el('span', 'legend', 'Follow-up'), dl);
      blocks.push(group);
    } else blocks.push(dl);
  }
  $('qt-delivery').replaceChildren(...blocks);
  pollGrade(i);
}

async function pollGrade(i) {
  const box = $('qt-content');
  box.replaceChildren(busy('p', 'Grading the content on this computer. You can move on; it will be in the track sheet.'));
  while (mode === 'quick-take' && index === i) {
    try {
      const data = await (await fetch(`/api/report/${session.session_id}`)).json();
      const a = data.answers[i];
      const f = a.follow_up;
      const followDone = !f || !f.transcript || ['graded', 'error'].includes(f.status);
      if (a.status === 'graded' && followDone) {
        const facts = el('dl', 'delivery');
        const d = el('div'), dd = el('dd', '', a.grade.final_score.toFixed(1));
        dd.append(el('small', '', ' / 10'));
        d.append(el('dt', 'legend', 'Content'), dd);
        facts.append(d);
        if (f?.grade?.score != null) {
          const fd = el('div'), fdd = el('dd', '', f.grade.score.toFixed(1));
          fdd.append(el('small', '', ' / 10'));
          fd.append(el('dt', 'legend', 'Follow-up'), fdd);
          facts.append(fd);
        }
        const fb = el('p', 'feedback');
        fb.append(el('strong', '', 'What to change: '), a.grade.feedback || '');
        box.replaceChildren(facts, fb);
        return;
      }
      if (a.status === 'error') { box.replaceChildren(el('p', 'take-error', a.grade?.error || 'Grading failed.')); return; }
    } catch { /* server busy: try again */ }
    await new Promise(r => setTimeout(r, 3000));
  }
}

$('done').addEventListener('click', () => {
  if (mode === 'speaking' || mode === 'reading' || mode === 'error') beginAnswer();
  else if (mode === 'listening') finishAnswer();
  else if (mode === 'quick-take') next();
});

$('skip').addEventListener('click', async () => {
  if (mode === 'listening') { mode = 'skipping'; live?.stop(); live = null; await recording.stop(); recording = null; }
  stopSpeaking();
  if (part === 'follow_up') {
    await fetch(`/api/skip-follow-up/${session.session_id}/${index}`, { method: 'POST' }).catch(() => {});
    afterQuestion();
  } else next();
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
// Load Whisper and the grading model while the student does the sound check.
fetch('/api/warmup', { method: 'POST' }).catch(() => {});
