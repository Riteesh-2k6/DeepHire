import { stopSpeaking } from './media.js';

const form = document.getElementById('settings');
const $ = id => document.getElementById(id);

function lamp(el, state, text) {
  el.hidden = false;
  el.dataset.state = state;
  el.querySelector('span:last-child').textContent = text;
}

// Fill the form from the saved settings.
const current = await (await fetch('/api/settings')).json();
for (const [name, value] of Object.entries(current)) {
  const radios = form.querySelectorAll(`input[type=radio][name="${name}"]`);
  if (radios.length) radios.forEach(r => { r.checked = r.value === String(value); });
  else if (form.elements[name]) form.elements[name].value = value;
}
$('speed-value').textContent = `${Number(current.tts_speed).toFixed(2)}×`;

function valueOf(input) {
  if (input.type === 'radio') {
    if (input.value === 'true' || input.value === 'false') return input.value === 'true';
    return /^\d+$/.test(input.value) ? Number(input.value) : input.value;
  }
  if (input.type === 'range') return Number(input.value);
  return input.value;
}

async function save(name, value) {
  lamp($('saved'), 'busy', 'Saving…');
  const r = await fetch('/api/settings', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ [name]: value }),
  });
  const data = await r.json().catch(() => ({}));
  if (r.ok) lamp($('saved'), 'ok', 'Saved');
  else lamp($('saved'), 'error', data.error || "Couldn't save that.");
}

// Radios and the slider save on change; text fields save when you leave them.
form.addEventListener('change', e => {
  const input = e.target;
  if (!input.name) return;
  if (input.type === 'range') $('speed-value').textContent = `${Number(input.value).toFixed(2)}×`;
  save(input.name, valueOf(input));
});
form.addEventListener('input', e => {
  if (e.target.type === 'range') $('speed-value').textContent = `${Number(e.target.value).toFixed(2)}×`;
});

$('sample').addEventListener('click', async () => {
  const btn = $('sample');
  btn.disabled = true;
  const voice = form.querySelector('input[name="tts_voice"]:checked')?.value;
  try {
    stopSpeaking();
    const r = await fetch('/api/speech', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: "Hi, I'm your interviewer. Let's start with a question about tries.", voice }),
    });
    if (!r.ok) throw new Error((await r.json().catch(() => ({}))).error || r.status);
    const audio = new Audio(URL.createObjectURL(await r.blob()));
    await audio.play();
    await new Promise(res => { audio.onended = res; });
  } catch (err) {
    lamp($('saved'), 'error', `No sample: ${err.message}`);
  }
  btn.disabled = false;
});

$('test-model').addEventListener('click', async () => {
  lamp($('test-result'), 'busy', 'Checking…');
  const r = await fetch('/api/settings/test-model', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ llm_base_url: form.elements.llm_base_url.value }),
  });
  const data = await r.json();
  if (!data.ok) return lamp($('test-result'), 'error', data.error);
  const wanted = form.elements.llm_model.value;
  lamp($('test-result'), data.models.includes(wanted) ? 'ok' : 'warn',
    data.models.includes(wanted) ? `Connected; ${wanted} is available` : `Connected, but it lists ${data.models.join(', ') || 'no models'}`);
});

$('open-folder').addEventListener('click', () => fetch('/api/open-data-folder', { method: 'POST' }));
