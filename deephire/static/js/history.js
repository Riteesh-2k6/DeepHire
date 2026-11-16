import { deleteSessionTakes } from './videos.js';

const $ = id => document.getElementById(id);
const dash = '—';
const when = iso => {
  const d = new Date(iso);
  return isNaN(d) ? iso || dash : d.toLocaleString(undefined, { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' });
};

function cell(text, cls) {
  const td = document.createElement('td');
  if (cls) td.className = cls;
  td.textContent = text ?? dash;
  return td;
}

function row(s) {
  const tr = document.createElement('tr');
  const sum = s.summary;
  const interview = document.createElement('td');
  interview.className = 'interview';
  const b = document.createElement('b');
  b.textContent = `${s.company} · ${s.domain}`;
  const span = document.createElement('span');
  span.textContent = `${s.difficulty} · ${s.mode === 'practice' ? 'Practice' : 'Mock'}`;
  interview.append(b, span);

  const status = document.createElement('td');
  const lamp = document.createElement('span');
  lamp.className = 'lamp';
  lamp.dataset.state = s.grading ? 'busy' : sum.answered ? 'ok' : '';
  const led = document.createElement('span');
  led.className = 'led';
  lamp.append(led, s.grading ? 'Grading…' : sum.answered ? 'Done' : 'Not started');
  status.append(lamp);

  const actions = document.createElement('td');
  actions.className = 'actions';
  const open = document.createElement('a');
  open.className = 'key';
  open.href = `/report?session=${s.session_id}`;
  open.textContent = 'Open';
  const del = document.createElement('button');
  del.className = 'key quiet';
  del.textContent = 'Delete';
  del.addEventListener('click', async () => {
    if (!confirm(`Delete this session (${s.company}, ${when(s.created_at)}) and its recordings? This cannot be undone.`)) return;
    del.disabled = true;
    const r = await fetch(`/api/sessions/${s.session_id}`, { method: 'DELETE' });
    if (r.ok) {
      await deleteSessionTakes(s.session_id).catch(() => {});
      tr.remove();
      if (!$('history-table').querySelector('tbody tr')) showEmpty();
    } else del.disabled = false;
  });
  actions.append(open, del);

  tr.append(cell(when(s.created_at)), interview, cell(`${sum.answered} of ${s.questions}`, 'n'),
    cell(sum.content_score != null ? sum.content_score.toFixed(1) : null, 'n'),
    cell(sum.wpm != null ? `${sum.wpm} wpm` : null, 'n'),
    cell(sum.camera_pct != null ? `${sum.camera_pct}%` : null, 'n'), status, actions);
  return tr;
}

function showEmpty() {
  $('history-table').hidden = true;
  $('history-empty').hidden = false;
}

async function load() {
  try {
    const { sessions } = await (await fetch('/api/sessions')).json();
    $('history-loading').hidden = true;
    if (!sessions.length) return showEmpty();
    $('history-table').querySelector('tbody').replaceChildren(...sessions.map(row));
    $('history-table').hidden = false;
  } catch {
    $('history-loading').textContent = "Couldn't load your sessions. Is DeepHire's engine still running?";
  }
}
load();
