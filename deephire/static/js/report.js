import { loadTake, deleteTake } from './videos.js';

const { session_id: id } = JSON.parse(document.getElementById('session-data').textContent);
const $ = sel => document.querySelector(sel);
const RUBRIC = [['technical_accuracy', 'Technical accuracy', 40], ['problem_solving', 'Problem solving', 30],
  ['completeness', 'Completeness', 20], ['optimization', 'Optimization', 10]];
const fmt = s => `${Math.floor(s / 60)}:${String(Math.round(s % 60)).padStart(2, '0')}`;
const dash = '—';

// Tiny DOM builder: everything from the transcript or the model goes in as text, never HTML.
function h(tag, attrs = {}, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v == null || v === false) continue;
    if (k === 'class') el.className = v;
    else if (k === 'style') el.style.cssText = v;
    else if (k.startsWith('on')) el.addEventListener(k.slice(2), v);
    else el.setAttribute(k, v);
  }
  el.append(...kids.flat().filter(k => k != null && k !== false));
  return el;
}

const STATUS = {
  unanswered: ['', 'Not answered'], grading: ['busy', 'Grading…'], graded: ['ok', 'Graded'], error: ['error', "Couldn't grade"],
};
const lamp = status => { const [state, text] = STATUS[status] || STATUS.unanswered; return h('span', { class: 'lamp', 'data-state': state }, h('span', { class: 'led' }), text); };
const inRange = (value, [lo, hi]) => value == null ? '' : value >= lo && value <= hi ? 'in-range' : 'out-range';

// ---------- the multitrack plot ----------
function lanes(data) {
  const answered = data.answers.filter(a => a.delivery);
  const maxT = Math.max(30, ...answered.map(a => a.delivery.duration_s));
  const pct = t => `${(100 * t / maxT).toFixed(3)}%`;
  const rows = data.answers.map((a, i) => {
    const track = h('div', { class: 'track' });
    if (!a.delivery) track.append(h('span', { class: 'empty' }, 'Not answered'));
    else if (!a.words?.length) track.append(h('span', { class: 'empty' }, 'No speech picked up'));
    else a.words.forEach((w, j) => {
      const next = a.words[j + 1];
      track.append(h('span', { class: /^(um+|uh+|uhm|er|erm|ah|hmm?|mm)\W*$/i.test(w.word) ? 'w filler' : 'w', style: `left:${pct(w.start)};width:${pct(w.end - w.start)}`, title: w.word }));
      if (next && next.start - w.end >= data.pause_s) {
        track.append(h('span', { class: 'gap', style: `left:${pct(w.end)};width:${pct(next.start - w.end)}` }, h('span', {}, `${(next.start - w.end).toFixed(1)}s`)));
      }
    });
    const score = a.grade?.final_score;
    return h('a', { class: 'lane', href: `#take-${i + 1}` },
      h('span', { class: 'take-label' }, `Take ${i + 1}`), track,
      h('span', { class: 'lane-end' }, score != null ? `${score.toFixed(1)}/10` : a.status === 'grading' ? '…' : dash,
        a.delivery?.wpm ? h('span', { class: 'wpm' }, ` · ${a.delivery.wpm} wpm`) : null));
  });
  const ticks = [];
  for (let t = 0; t <= maxT; t += maxT > 120 ? 30 : 15) ticks.push(h('span', { style: `left:${pct(t)}` }, fmt(t)));
  return [...rows, h('div', { class: 'axis' }, h('span'), h('div', { class: 'ticks' }, ticks), h('span'))];
}

// ---------- totals ----------
function totals(data) {
  const s = data.summary, r = data.ranges;
  const cell = (legend, value, unit, note, cls = '') => h('div', { class: 'total' },
    h('span', { class: 'legend' }, legend),
    h('span', { class: `value ${cls}` }, value ?? dash, value != null && unit ? h('small', {}, ` ${unit}`) : null),
    h('span', { class: 'note' }, note));
  return [
    cell('Content', s.content_score?.toFixed(1), '/ 10', `graded ${s.graded} of ${s.answered} answers`),
    cell('Pace', s.wpm, 'wpm', `guide ${r.wpm[0]}–${r.wpm[1]}`, inRange(s.wpm, r.wpm)),
    cell('Pauses', s.answered ? s.pause_count : null, '', `of ${data.pause_s} s or more, all answers`),
    cell('Fillers', s.fillers_per_min, '/ min', 'a lower bound', inRange(s.fillers_per_min, r.fillers_per_min)),
    cell('On camera', s.camera_pct, '%', s.camera_pct == null ? 'no camera data' : `rule of thumb ${r.camera_pct[0]}%+`, inRange(s.camera_pct, r.camera_pct)),
  ];
}

// ---------- track sheet rows ----------
function sheetRow(a, i) {
  const d = a.delivery || {};
  const n = v => h('td', { class: 'n' }, v ?? dash);
  return h('tr', { 'data-status': a.status },
    h('td', {}, h('b', {}, `${i + 1}`)),
    h('td', { class: 'q' }, h('a', { href: `#take-${i + 1}` }, a.question)),
    n(a.delivery ? fmt(d.duration_s) : null), n(d.wpm), n(a.delivery ? d.pause_count : null),
    n(d.fillers_per_min), n(d.camera_pct != null ? `${d.camera_pct}%` : null),
    n(a.grade?.final_score != null ? a.grade.final_score.toFixed(1) : null),
    h('td', {}, lamp(a.status)));
}

// ---------- one take ----------
function transcript(a, pauseS) {
  if (!a.words?.length) return h('p', { class: 'transcript' }, a.delivery ? 'No speech was picked up in this take.' : '');
  const out = [];
  if (a.words[0].start >= pauseS) out.push(h('span', { class: 'pause' }, `started after ${a.words[0].start.toFixed(1)} s`), ' ');
  a.words.forEach((w, j) => {
    const filler = /^(um+|uh+|uhm|er|erm|ah|hmm?|mm)\W*$/i.test(w.word);
    out.push(filler ? h('span', { class: 'filler' }, w.word) : w.word, ' ');
    const next = a.words[j + 1];
    if (next && next.start - w.end >= pauseS) out.push(h('span', { class: 'pause' }, `${(next.start - w.end).toFixed(1)} s`), ' ');
  });
  return h('div', {}, h('p', { class: 'transcript' }, out),
    h('p', { class: 'transcript-note' }, 'Transcribed on this computer; small recognition slips are possible.'));
}

function bars(score, cls = '') {
  return h('span', { class: `bars ${cls}`, role: 'img', 'aria-label': `${score} out of 10` },
    Array.from({ length: 10 }, (_, k) => h('i', { class: k < Math.round(score) ? 'on' : '' })));
}

function grading(a, i, data) {
  if (a.status === 'grading') return h('div', { class: 'scores' }, h('p', { class: 'take-state' }, lamp('grading'), 'The local model is grading this answer. This page updates on its own.'),
    h('div', { class: 'skeleton', style: 'width:70%' }), h('div', { class: 'skeleton', style: 'width:55%' }));
  if (a.status === 'error') return h('div', { class: 'scores' },
    h('p', { class: 'take-error' }, a.grade?.error || 'Grading failed.'),
    h('div', {}, h('button', { class: 'key', onclick: e => regrade(i, e.currentTarget) }, h('span', { class: 'led' }), 'Grade again')));
  const g = a.grade;
  if (!g) {  // skipped: same furniture as every take, with dashes
    return h('div', { class: 'scores' }, [...RUBRIC, ['clarity', 'Clarity', null]].map(([, label, weight]) =>
      h('div', { class: weight ? 'score-row' : 'score-row side' },
        h('span', { class: 'legend' }, label, h('span', { class: 'weight' }, weight ? `${weight}%` : 'not weighted')),
        bars(0), h('span', { class: 'num' }, dash), h('span', { class: 'why' }, 'Not answered'))));
  }
  return [
    h('div', { class: 'scores' },
      RUBRIC.map(([key, label, weight]) => h('div', { class: 'score-row' },
        h('span', { class: 'legend' }, label, h('span', { class: 'weight' }, `${weight}%`)),
        bars(g[key].score), h('span', { class: 'num' }, g[key].score),
        h('span', { class: 'why' }, g[key].justification))),
      h('div', { class: 'score-row side' },
        h('span', { class: 'legend' }, 'Clarity', h('span', { class: 'weight' }, 'not weighted')),
        bars(g.clarity.score), h('span', { class: 'num' }, g.clarity.score),
        h('span', { class: 'why' }, g.clarity.justification))),
    g.feedback ? h('p', { class: 'feedback' }, h('strong', {}, 'What to change: '), g.feedback) : null,
    g.model_answer ? h('details', { class: 'model' }, h('summary', {}, 'A strong answer, for comparison'), h('p', {}, g.model_answer)) : null,
  ];
}

function deliveryList(a, data) {
  const has = Boolean(a.delivery), d = a.delivery || {};
  const r = data.ranges;
  const item = (label, value, note, cls = '') => h('div', {}, h('dt', { class: 'legend' }, label),
    h('dd', { class: cls }, value ?? dash, note ? h('small', {}, ` ${note}`) : null));
  return h('dl', { class: 'delivery' },
    item('Length', has ? fmt(d.duration_s) : null),
    item('Started after', d.first_word_s != null ? `${d.first_word_s} s` : null),
    item('Pace', d.wpm, d.wpm ? `wpm (guide ${r.wpm[0]}–${r.wpm[1]})` : has ? 'too short to measure' : '', inRange(d.wpm, r.wpm)),
    item('Pauses', has ? d.pause_count : null, d.pause_count ? `longest ${d.longest_pause_s} s` : ''),
    item('Fillers', has ? d.filler_count : null, d.fillers_per_min != null ? `${d.fillers_per_min}/min` : ''),
    item('On camera', d.camera_pct != null ? `${d.camera_pct}%` : null, d.face_pct != null ? `face in frame ${d.face_pct}%` : has ? 'no camera data' : '', inRange(d.camera_pct, r.camera_pct)));
}

const takeEls = new Map();
function take(a, i, data) {
  let el = takeEls.get(i);
  if (!el) {
    el = h('article', { class: 'take paper', id: `take-${i + 1}` },
      h('header', { class: 'take-head' }, h('h2', {}, `Take ${i + 1}`), h('span', { class: 'slot-state' })),
      h('p', { class: 'take-q' }, a.question),
      h('div', { class: 'take-grid' }, h('div', { class: 'replay' }), h('div', { class: 'slot-transcript' })),
      h('div', { class: 'slot-delivery' }), h('div', { class: 'slot-grade', style: 'display:grid;gap:1rem' }));
    takeEls.set(i, el);
    if (a.delivery) replay(el.querySelector('.replay'), i);   // once: re-rendering would restart playback
    else el.querySelector('.replay').replaceChildren(h('p', { class: 'absent well' }, 'Skipped, nothing recorded.'));
  }
  el.querySelector('.slot-state').replaceChildren(lamp(a.status));
  el.querySelector('.slot-transcript').replaceChildren(a.delivery ? transcript(a, data.pause_s) : h('p', { class: 'transcript-note' }, 'This question was skipped.'));
  el.querySelector('.slot-delivery').replaceChildren(deliveryList(a, data));
  el.querySelector('.slot-grade').replaceChildren(...[grading(a, i, data)].flat().filter(Boolean));
  return el;
}

async function replay(slot, i) {
  const blob = await loadTake(id, i);
  if (!blob) {
    slot.replaceChildren(h('p', { class: 'absent well' }, 'No recording on this device. Recordings stay in the browser that made them.'));
    return;
  }
  const url = URL.createObjectURL(blob);
  slot.replaceChildren(
    h('video', { src: url, controls: '', preload: 'metadata', playsinline: '' }),
    h('div', { class: 'replay-actions' },
      h('a', { class: 'key', href: url, download: `deephire-take-${i + 1}.webm` }, 'Download'),
      h('button', { class: 'key quiet', onclick: async () => {
        if (!confirm('Delete this recording from this browser? This cannot be undone.')) return;
        await deleteTake(id, i);
        URL.revokeObjectURL(url);
        replay(slot, i);
      } }, 'Delete recording')));
}

async function regrade(i, button) {
  button.disabled = true;
  await fetch(`/api/regrade/${id}/${i}`, { method: 'POST' });
  refresh();
}

// ---------- refresh loop ----------
let timer;
async function refresh() {
  clearTimeout(timer);
  let data;
  try {
    const r = await fetch(`/api/report/${id}`);
    if (!r.ok) throw new Error(r.status);
    data = await r.json();
  } catch {
    $('#grading-note').hidden = false;
    $('#grading-note').dataset.state = 'error';
    $('#grading-note span:last-child').textContent = "Can't reach the DeepHire server. Retrying…";
    timer = setTimeout(refresh, 5000);
    return;
  }
  $('#lanes').replaceChildren(...lanes(data));
  $('#totals').replaceChildren(...totals(data));
  $('#sheet tbody').replaceChildren(...data.answers.map(sheetRow));
  $('#takes').replaceChildren(...data.answers.map((a, i) => take(a, i, data)));

  const note = $('#grading-note');
  note.hidden = !data.grading;
  note.dataset.state = 'busy';
  note.querySelector('span:last-child').textContent =
    `Grading ${data.grading} ${data.grading === 1 ? 'answer' : 'answers'} on the local model. This page fills in as they finish.`;
  if (data.grading) timer = setTimeout(refresh, 3000);
}
refresh();
