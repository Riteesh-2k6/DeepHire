// Browser-only media helpers: the interviewer's voice, the mic level, live audio chunks, and recording.

// ---- the interviewer's voice ----
// First choice: Kokoro on the local server (/api/speech), one sentence at a time so speech starts at once.
// Fallback: the browser's own voices, local ones only (cloud voices would send the text away).
let audioCtx = null, voiceAnalyser = null, voiceBuf = null, currentSource = null, serverVoice = true, voiceFailures = 0;

function context() {
  if (!audioCtx) {
    audioCtx = new AudioContext();
    voiceAnalyser = audioCtx.createAnalyser();
    voiceAnalyser.fftSize = 1024;
    voiceAnalyser.connect(audioCtx.destination);
    voiceBuf = new Float32Array(voiceAnalyser.fftSize);
  }
  return audioCtx;
}

// The interviewer's loudness right now (0..~0.5), so the dial moves with the real voice.
export function voiceLevel() {
  if (!voiceAnalyser || !currentSource) return 0;
  voiceAnalyser.getFloatTimeDomainData(voiceBuf);
  let sum = 0;
  for (const x of voiceBuf) sum += x * x;
  return Math.sqrt(sum / voiceBuf.length);
}

// Same split as tts.sentences() on the server, so pre-voiced pieces are found in its cache.
export const sentences = text => {
  const t = text.replace(/\s+/g, ' ').trim();
  const out = [];
  for (const s of t.split(/(?<=[.!?])\s+/)) {
    if (!s) continue;
    if (s.split(' ').length <= 14) { out.push(s); continue; }
    let buf = [];                                        // comma pieces merged into 8+ word chunks
    for (const p of s.split(/(?<=,)\s+/)) {
      buf.push(p);
      if (buf.join(' ').split(' ').length >= 8) { out.push(buf.join(' ')); buf = []; }
    }
    if (buf.length) out.push(buf.join(' '));
  }
  return out.length ? out : (t ? [t] : []);
};

const fetchSpeech = sentence => fetch('/api/speech', {
  method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text: sentence }),
}).then(r => (r.ok ? r.arrayBuffer() : Promise.reject(new Error(`speech ${r.status}`))));

// Ask the server to voice text in the background (it caches); returns at once, nothing is played.
export function prefetchSpeech(text) {
  if (serverVoice) {
    fetch('/api/speech/ahead', { method: 'POST', headers: { 'Content-Type': 'application/json' },
                                 body: JSON.stringify({ text }) }).catch(() => {});
  }
}

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
  try { currentSource?.stop(); } catch { /* already ended */ }
  currentSource = null;
  if ('speechSynthesis' in window) speechSynthesis.cancel();
}

async function playBuffer(arrayBuffer, run) {
  const buffer = await context().decodeAudioData(arrayBuffer);
  if (run.cancelled) return;
  await new Promise(resolve => {
    const src = audioCtx.createBufferSource();
    src.buffer = buffer;
    src.connect(voiceAnalyser);
    src.onended = () => { if (currentSource === src) currentSource = null; resolve(); };
    currentSource = src;
    src.start();
  });
}

async function speakWithBrowser(text, run, onWord) {
  const voice = await localVoice();
  if (!voice) return false;                              // caption only
  for (const sentence of sentences(text)) {
    if (run.cancelled) break;
    await new Promise(resolve => {
      const u = new SpeechSynthesisUtterance(sentence);
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

// Speaks text; resolves true when finished, false if cancelled or no voice exists.
export async function speak(text, onWord = () => {}) {
  stopSpeaking();
  const run = speaking = { cancelled: false };
  if (serverVoice) {
    try {
      await context().resume();
      const parts = sentences(text);
      const pending = parts.map(fetchSpeech);           // all requested now; the server voices them in order
      pending.forEach(p => p.catch(() => {}));
      for (const p of pending) {
        if (run.cancelled) return false;
        await playBuffer(await p, run);
      }
      return !run.cancelled;
    } catch (err) {
      console.warn('local voice unavailable for this line, using the browser voice', err);
      if (String(err.message).includes('503 ') || ++voiceFailures >= 3) serverVoice = false;
      if (run.cancelled) return false;
    }
  }
  return speakWithBrowser(text, run, onWord);
}

// ---- mic level ----
export function micMeter(stream) {
  const ctx = new AudioContext();
  const analyser = ctx.createAnalyser();
  analyser.fftSize = 1024;
  const source = ctx.createMediaStreamSource(stream);
  source.connect(analyser);
  const buf = new Float32Array(analyser.fftSize);
  return {
    level() {                                            // RMS, roughly 0..0.5 for speech
      analyser.getFloatTimeDomainData(buf);
      let sum = 0;
      for (const x of buf) sum += x * x;
      return Math.sqrt(sum / buf.length);
    },
    resume: () => ctx.resume(),
    // Live audio for transcription: 16 kHz 16-bit chunks every `seconds`, passed to send(int16, seq).
    async liveChunks(send, seconds = 1.5) {
      await ctx.audioWorklet.addModule('/static/js/pcm-worklet.js');
      const tap = new AudioWorkletNode(ctx, 'pcm-tap');
      const mute = ctx.createGain();
      mute.gain.value = 0;                               // the tap must be pulled, but we don't want to hear it
      source.connect(tap).connect(mute).connect(ctx.destination);
      const ratio = ctx.sampleRate / 16000;
      let pos = 0, out = [], seq = 0;
      tap.port.onmessage = e => {                        // linear-interpolation resampling to 16 kHz
        const x = e.data;
        while (pos < x.length - 1) {
          const i = Math.floor(pos), f = pos - i;
          out.push(x[i] + (x[i + 1] - x[i]) * f);
          pos += ratio;
        }
        pos -= x.length - 1;
        if (out.length >= 16000 * seconds) flush();
      };
      const flush = () => {
        if (!out.length) return;
        const pcm = new Int16Array(out.length);
        for (let i = 0; i < out.length; i++) pcm[i] = Math.max(-32768, Math.min(32767, out[i] * 32768));
        out = [];
        send(pcm, seq++);
      };
      return {
        stop() {
          tap.port.onmessage = null;
          flush();                                       // the last partial chunk
          try { source.disconnect(tap); tap.disconnect(); mute.disconnect(); } catch { /* already gone */ }
        },
      };
    },
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
