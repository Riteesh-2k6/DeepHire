// Browser-only media helpers: the interviewer's voice, the mic level, and recording.

// ---- the interviewer's voice: local OS voices only (cloud voices would send the text away) ----
function voicesReady() {
  if (!('speechSynthesis' in window)) return Promise.resolve([]);
  const now = speechSynthesis.getVoices();
  if (now.length) return Promise.resolve(now);
  return new Promise(resolve => {
    const done = () => resolve(speechSynthesis.getVoices());
    speechSynthesis.addEventListener('voiceschanged', done, { once: true });
    setTimeout(done, 1500);
  });
}

export async function localVoice() {
  const voices = (await voicesReady()).filter(v => v.localService && v.lang.toLowerCase().startsWith('en'));
  return voices.find(v => /en[-_](in|gb|us)/i.test(v.lang)) || voices[0] || null;
}

let speaking = null;
export function stopSpeaking() {
  if (speaking) speaking.cancelled = true;
  if ('speechSynthesis' in window) speechSynthesis.cancel();
}

// Reads text aloud sentence by sentence (Chrome cuts long utterances short).
// onWord fires on each word boundary so the UI can move with the voice.
export async function speak(text, onWord = () => {}) {
  stopSpeaking();
  const voice = await localVoice();
  if (!voice) return false;                              // caption only
  const run = speaking = { cancelled: false };
  for (const sentence of text.match(/[^.!?]+[.!?]*/g) || [text]) {
    if (run.cancelled) break;
    await new Promise(resolve => {
      const u = new SpeechSynthesisUtterance(sentence.trim());
      u.voice = voice;
      u.rate = 1;
      u.onboundary = e => e.name !== 'sentence' && onWord();
      u.onend = u.onerror = () => { clearTimeout(guard); resolve(); };
      // Some browsers never fire onend; don't let that freeze the interview.
      const guard = setTimeout(resolve, 1500 + sentence.split(/\s+/).length * 550);
      speechSynthesis.speak(u);
    });
  }
  return !run.cancelled;
}

// ---- mic level ----
export function micMeter(stream) {
  const ctx = new AudioContext();
  const analyser = ctx.createAnalyser();
  analyser.fftSize = 1024;
  ctx.createMediaStreamSource(stream).connect(analyser);
  const buf = new Float32Array(analyser.fftSize);
  return {
    level() {                                            // RMS, roughly 0..0.5 for speech
      analyser.getFloatTimeDomainData(buf);
      let sum = 0;
      for (const x of buf) sum += x * x;
      return Math.sqrt(sum / buf.length);
    },
    resume: () => ctx.resume(),
  };
}

// ---- recording ----
const pick = types => types.find(t => window.MediaRecorder && MediaRecorder.isTypeSupported(t)) || '';

// Records the full stream (kept locally for replay) and an audio-only copy (sent to the local server).
export function startRecording(stream) {
  const replay = new MediaRecorder(stream, {
    mimeType: pick(['video/webm;codecs=vp9,opus', 'video/webm;codecs=vp8,opus', 'video/webm', 'audio/webm']),
    videoBitsPerSecond: 1_000_000,
  });
  const audio = new MediaRecorder(new MediaStream(stream.getAudioTracks()), {
    mimeType: pick(['audio/webm;codecs=opus', 'audio/webm', 'audio/ogg;codecs=opus']),
  });
  // A recorder can stop or error on its own (say the camera is unplugged mid-answer); keep what it got.
  const collect = rec => {
    const parts = [];
    let finish;
    const blob = new Promise(resolve => { finish = () => resolve(new Blob(parts, { type: rec.mimeType })); });
    rec.ondataavailable = e => e.data.size && parts.push(e.data);
    rec.onstop = rec.onerror = () => finish();
    return { blob, finish };
  };
  const r1 = collect(replay), r2 = collect(audio);
  replay.start(1000);
  audio.start(1000);
  const started = performance.now();
  return {
    async stop() {
      for (const rec of [replay, audio]) {
        try { if (rec.state !== 'inactive') rec.stop(); } catch { /* already stopped */ }
      }
      setTimeout(() => { r1.finish(); r2.finish(); }, 3000);   // never wait forever for onstop
      const [video, voice] = await Promise.all([r1.blob, r2.blob]);
      return { video, voice, duration: (performance.now() - started) / 1000 };
    },
  };
}
