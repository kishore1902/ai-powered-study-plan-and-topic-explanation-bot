(function () {
'use strict';
if (!GF.requireLogin()) return;

let chatLog = [];
let quizPreset = null;
let tab = 'materials';

/* ---------- helpers ---------- */
const $ = (s, r) => (r || document).querySelector(s);
const $$ = (s, r) => [...(r || document).querySelectorAll(s)];
const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const pct = x => Math.round(x * 100);
const pill = lv => '<span class="pill ' + lv + '">' + lv + '</span>';
const TYPE_NAME = { syllabus: 'Syllabus', notes: 'Notes / textbook', past: 'Past paper' };
const api = GF.api;

let toastT;
function toast(m, err) {
  const t = $('#toast');
  t.textContent = m; t.className = 'toast show' + (err ? ' err' : '');
  clearTimeout(toastT); toastT = setTimeout(() => { t.className = 'toast'; }, err ? 6000 : 2600);
}
async function run(btn, label, fn) {
  const old = btn.textContent;
  btn.disabled = true; btn.textContent = label;
  try { await fn(); } catch (e) { console.error(e); toast(e.message || String(e), true); }
  finally { if (btn.isConnected) { btn.disabled = false; btn.textContent = old; } }
}
const loading = () => { $('#view').innerHTML = '<p class="muted">Loading…</p>'; };

/* ---------- shell ---------- */
const TABS = [['materials', 'Materials'], ['topics', 'Topic map'], ['quiz', 'Diagnostic quiz'], ['gaps', 'Gap report'], ['plan', 'Revision plan'], ['explain', 'Explain a topic'], ['progress', 'Progress'], ['how', 'How it works'], ['settings', 'Settings']];
const VIEWS = { materials: viewMaterials, topics: viewTopics, quiz: viewQuiz, gaps: viewGaps, plan: viewPlan, explain: viewExplain, progress: viewProgress, how: viewHow, settings: viewSettings };

function render() {
  tab = location.hash.slice(1) || 'materials';
  if (!VIEWS[tab]) tab = 'materials';
  $('#tabs').innerHTML = TABS.map(t => '<button data-t="' + t[0] + '" class="' + (t[0] === tab ? 'on' : '') + '">' + t[1] + '</button>').join('');
  $$('#tabs button').forEach(b => { b.onclick = () => { location.hash = b.dataset.t; }; });
  $('#banner').innerHTML = (!GF.getKey() && tab !== 'settings' && tab !== 'how')
    ? '<div class="banner">Add your Groq API key in <a href="#settings">Settings</a> to use AI features.</div>' : '';
  window.scrollTo(0, 0);
  VIEWS[tab]().catch(e => { $('#view').innerHTML = '<div class="card bad">' + esc(e.message) + '</div>'; });
}

/* ---------- Materials ---------- */
async function viewMaterials() {
  loading();
  const { docs } = await api('/docs');
  const list = docs.map(d => '<div class="row"><b>' + esc(d.name) + '</b><span class="tag">' + TYPE_NAME[d.type] + '</span><span class="muted">' + d.chunks + ' passages</span><span style="flex:1"></span><button class="link" data-del="' + d.id + '">Remove</button></div>').join('') || '<p class="muted">Nothing uploaded yet.</p>';
  $('#view').innerHTML =
    '<div class="card"><h2>Upload your material</h2>' +
    '<p class="muted">PDF, .txt or .md (up to 4 MB per file). Start with the syllabus (it becomes the topic map), then notes or textbook chapters, then past papers.</p>' +
    '<label>Type<select id="up-type"><option value="syllabus">Syllabus</option><option value="notes" selected>Notes / textbook chapter</option><option value="past">Past question paper</option></select></label>' +
    '<input type="file" id="up-file" multiple accept=".pdf,.txt,.md,text/plain,application/pdf">' +
    '<button id="up-btn">Add files</button>' +
    '<details style="margin-top:1rem"><summary class="muted">…or paste text</summary><div style="margin-top:.6rem"><input id="paste-name" placeholder="Title, e.g. Unit 3 notes"><textarea id="paste-text" placeholder="Paste text here"></textarea><button class="sec" id="paste-btn">Add pasted text</button></div></details>' +
    '<p style="margin:1rem 0 0"><button class="sec" id="sample-btn">Load sample material (Operating Systems)</button></p></div>' +
    '<div class="card"><h3>Your material</h3>' + list + '</div>';

  $('#up-btn').onclick = e => run(e.target, 'Reading…', async () => {
    const files = [...$('#up-file').files];
    if (!files.length) throw new Error('Choose at least one file.');
    const fd = new FormData();
    fd.append('type', $('#up-type').value);
    files.forEach(f => fd.append('files', f));
    await api('/docs', { method: 'POST', form: fd });
    toast('Added ' + files.length + ' file(s).'); viewMaterials();
  });
  $('#paste-btn').onclick = e => run(e.target, 'Adding…', async () => {
    const t = $('#paste-text').value.trim();
    if (!t) throw new Error('Paste some text first.');
    await api('/docs/text', { method: 'POST', body: { name: $('#paste-name').value, type: $('#up-type').value, text: t } });
    toast('Added.'); viewMaterials();
  });
  $('#sample-btn').onclick = e => run(e.target, 'Loading…', async () => {
    await api('/docs/sample', { method: 'POST' });
    toast('Sample loaded. Next: build the topic map.'); viewMaterials();
  });
  $$('[data-del]').forEach(b => { b.onclick = () => run(b, '…', async () => { await api('/docs/' + b.dataset.del, { method: 'DELETE' }); viewMaterials(); }); });
}

/* ---------- Topic map ---------- */
async function viewTopics() {
  loading();
  const d = await api('/topics');
  let list = '<p class="muted">No topic map yet.' + (d.has_syllabus ? '' : ' Upload a syllabus first.') + '</p>';
  if (d.topics.length) {
    list = '<div class="grid">' + d.topics.map(t =>
      '<div class="card" style="margin:0"><b>' + esc(t.name) + '</b> ' + pill(t.level) +
      '<ul>' + t.sub.map(s => '<li>' + esc(s) + '</li>').join('') + '</ul>' +
      '<div class="muted" style="font-size:.85rem">Past-paper questions mapped: <b>' + t.past_hits + '</b><br>' +
      (d.has_notes ? (t.covered ? 'Material found in your notes' : '<span class="bad">No matching passage in your notes</span>') : 'No notes uploaded yet') + '</div></div>').join('') + '</div>';
  }
  $('#view').innerHTML =
    '<div class="card"><h2>Topic map</h2><p class="muted"><span class="tag gen">generation</span> reads your syllabus text and lists its topics. <span class="tag ret">retrieval</span> then maps each past-paper question to the closest topic.</p>' +
    '<button id="build"' + (d.has_syllabus ? '' : ' disabled') + '>' + (d.topics.length ? 'Rebuild from syllabus' : 'Build topic map from syllabus') + '</button></div>' + list;
  $('#build').onclick = e => run(e.target, 'Reading syllabus…', async () => { await api('/topics/build', { method: 'POST' }); toast('Topic map ready.'); viewTopics(); });
}

/* ---------- Quiz ---------- */
function resultCard(a) {
  const items = a.results.map((r, i) => {
    const ok = r.score >= 1, part = r.score > 0 && r.score < 1;
    return '<div class="q"><div class="muted"><span class="tag">' + esc(r.topic_name) + '</span> <span class="' + (ok ? 'good' : part ? '' : 'bad') + '">' + (ok ? '✓ correct' : part ? '◐ partly correct' : '✗ incorrect') + '</span></div>' +
      '<b>Q' + (i + 1) + '. ' + esc(r.question) + '</b>' +
      '<div>Your answer: ' + esc(r.chosen || '(blank)') + '</div>' + (ok ? '' : '<div>Correct answer: ' + esc(r.correct_text) + '</div>') +
      '<div class="muted"><span class="tag gen">explanation</span> ' + esc(r.explanation) + '</div>' +
      '<div class="src"><span class="tag ret">source</span> ' + esc(r.label) + '<br>' + (r.quote ? '“' + esc(r.quote) + '”' : esc(r.snippet) + '…') + '</div></div>';
  }).join('');
  return '<div class="card"><h2>Last result: ' + a.pct + '%</h2><p><a href="#gaps">See your gap report →</a></p>' + items + '</div>';
}

async function viewQuiz() {
  loading();
  const d = await api('/quiz');
  if (d.quiz) return renderQuizForm(d.quiz);
  if (!d.topics.length) { $('#view').innerHTML = '<div class="card">Build the <a href="#topics">topic map</a> first.</div>'; return; }
  const preset = quizPreset || d.topics.slice(0, 6).map(t => t.id);
  quizPreset = null;
  $('#view').innerHTML = '<div class="card"><h2>Diagnostic quiz</h2><p class="muted"><span class="tag ret">retrieval</span> finds the best passages in your notes for each topic, then <span class="tag gen">generation</span> writes questions from only those passages. Each question cites its source section.</p>' +
    d.topics.map(t => '<label class="row" style="cursor:pointer"><input type="checkbox" class="tsel" style="width:auto;margin:0" value="' + esc(t.id) + '"' + (preset.includes(t.id) ? ' checked' : '') + '> ' + esc(t.name) + ' ' + pill(t.level) + '</label>').join('') +
    '<label style="margin-top:.8rem">Questions per topic<select id="per"><option>1</option><option selected>2</option><option>3</option></select></label>' +
    '<p class="muted" style="font-size:.85rem">Tip: up to 8 topics at a time; 6 keeps you inside free-tier Groq limits.</p>' +
    '<button id="gen">Generate quiz</button></div>' + (d.last_result ? resultCard(d.last_result) : '');
  $('#gen').onclick = e => run(e.target, 'Retrieving + generating…', async () => {
    const ids = $$('.tsel').filter(c => c.checked).map(c => c.value);
    if (!ids.length) throw new Error('Select at least one topic.');
    const r = await api('/quiz/generate', { method: 'POST', body: { topic_ids: ids, per: Number($('#per').value) } });
    if (r.skipped.length) toast('No matching material for: ' + r.skipped.join(', '), true);
    viewQuiz();
  });
}

function renderQuizForm(quiz) {
  const Q = quiz.questions;
  $('#view').innerHTML = '<div class="card"><h2>Diagnostic quiz</h2><p class="muted">' + Q.length + ' questions. Answer without looking at your notes.</p>' +
    Q.map((q, i) => {
      const body = q.type === 'mcq'
        ? q.options.map((o, j) => '<label><input type="radio" name="q' + i + '" value="' + j + '"> ' + esc(o) + '</label>').join('')
        : '<textarea name="q' + i + '" placeholder="Answer in 1-2 sentences"></textarea>';
      return '<div class="q"><div class="muted"><span class="tag">' + esc(q.topic_name) + '</span> <span class="tag gen">generated</span> <span class="tag ret">cites ' + esc(q.label) + '</span></div><b>Q' + (i + 1) + '. ' + esc(q.question) + '</b>' + body + '</div>';
    }).join('') +
    '<p style="margin-top:1rem"><button id="submit">Submit answers</button> <button class="sec" id="discard">Discard quiz</button></p></div>';
  $('#discard').onclick = e => run(e.target, '…', async () => { await api('/quiz', { method: 'DELETE' }); viewQuiz(); });
  $('#submit').onclick = e => run(e.target, 'Grading…', async () => {
    const answers = Q.map((q, i) => {
      if (q.type === 'mcq') { const c = $('input[name="q' + i + '"]:checked'); return c ? Number(c.value) : null; }
      return $('textarea[name="q' + i + '"]').value;
    });
    const r = await api('/quiz/submit', { method: 'POST', body: { answers } });
    (r.warnings || []).forEach(w => toast(w, true));
    viewQuiz();
  });
}

/* ---------- Gap report ---------- */
async function viewGaps() {
  loading();
  const d = await api('/gaps');
  if (!d.ready) { $('#view').innerHTML = '<div class="card"><h2>Gap report</h2><p class="muted">Take a <a href="#quiz">diagnostic quiz</a> to see your weak, medium and strong topics.</p></div>'; return; }
  const c = d.counts;
  $('#view').innerHTML = '<div class="card"><h2>Gap report</h2>' +
    '<p>' + pill('weak') + ' ' + c.weak + ' &nbsp; ' + pill('medium') + ' ' + c.medium + ' &nbsp; ' + pill('strong') + ' ' + c.strong + ' &nbsp; ' + pill('untested') + ' ' + c.untested + '</p>' +
    '<p class="muted" style="font-size:.85rem">Mastery is calculated by code from your answers (latest attempt counts 60%). The reasons are written by the model from your actual mistakes.</p>' +
    '<table><tr><th>Topic</th><th>Level</th><th>Mastery</th><th>Why</th></tr>' +
    d.rows.map(r => '<tr><td><b>' + esc(r.name) + '</b><div class="muted" style="font-size:.8rem">' + (r.answered ? r.answered + ' question(s) answered' : '') + (r.past_hits ? ' · in ' + r.past_hits + ' past-paper question(s)' : '') + '</div></td><td>' + pill(r.level) + '</td><td>' + (r.mastery == null ? '–' : pct(r.mastery) + '%') + '</td><td>' + esc(r.why) + '</td></tr>').join('') + '</table>' +
    '<p style="margin-top:1rem"><button id="retest">Retest weak and medium topics</button> <a href="#plan" style="margin-left:.6rem">Open revision plan →</a></p></div>';
  $('#retest').onclick = () => {
    const ids = d.rows.filter(r => r.level !== 'strong').map(r => r.id).slice(0, 6);
    quizPreset = ids.length ? ids : null; location.hash = 'quiz';
  };
}

/* ---------- Revision plan ---------- */
const fmt = mn => mn >= 60 ? Math.floor(mn / 60) + 'h' + (mn % 60 ? ' ' + (mn % 60) + 'm' : '') : mn + 'm';
async function viewPlan(data) {
  if (!data) { loading(); data = await api('/plan'); }
  const d = data;
  if (!d.ready) { $('#view').innerHTML = '<div class="card"><h2>Revision plan</h2><p class="muted">Build the <a href="#topics">topic map</a> first.</p></div>'; return; }
  $('#view').innerHTML = '<div class="card"><h2>Revision plan</h2>' +
    '<p class="muted"><span class="tag ret">retrieval</span> picks what to re-read; priority and minutes are calculated by code (weakness × past-paper frequency); <span class="tag gen">generation</span> only writes the study tips.</p>' +
    '<div class="grid"><label>Days until exam<input type="number" id="days" min="1" max="60" value="' + d.days + '"></label><label>Hours per day<input type="number" id="hours" min="0.5" max="12" step="0.5" value="' + d.hours + '"></label></div>' +
    '<button id="apply">Update plan</button> <button class="sec" id="tips">' + (d.has_tips ? 'Refresh' : 'Generate') + ' AI study tips</button>' + (d.tips_stale ? ' <span class="muted">Tips are from an older attempt.</span>' : '') + '</div>' +
    '<div class="card"><h3>Priority order</h3><table><tr><th>#</th><th>Topic</th><th>Level</th><th>Time</th><th>Re-read and tips</th></tr>' +
    d.rows.map((r, i) => '<tr><td>' + (i + 1) + '</td><td><b>' + esc(r.name) + '</b></td><td>' + pill(r.level) + '</td><td>' + fmt(r.min) + (r.overflow ? '<div class="bad" style="font-size:.8rem">' + fmt(r.overflow) + ' does not fit</div>' : '') + '</td><td>' +
      (r.reread.length ? '<div class="muted"><span class="tag ret">re-read</span> ' + r.reread.map(esc).join('; ') + '</div>' : '') +
      (r.tips.length ? '<ul>' + r.tips.map(a => '<li>' + esc(a) + '</li>').join('') + '</ul>' : '') + '</td></tr>').join('') + '</table></div>' +
    '<div class="card"><h3>Day by day</h3>' + d.schedule.map(day => '<div class="row"><b style="min-width:3.5rem">Day ' + day.n + '</b><span>' + day.slots.map(s => esc(s.name) + ' (' + fmt(s.min) + ')').join(' · ') + '</span></div>').join('') + '</div>';
  $('#apply').onclick = e => run(e.target, '…', async () => {
    viewPlan(await api('/plan', { method: 'PUT', body: { days: parseInt($('#days').value, 10) || 14, hours: parseFloat($('#hours').value) || 2 } }));
  });
  $('#tips').onclick = e => run(e.target, 'Writing tips…', async () => { viewPlan(await api('/plan/tips', { method: 'POST' })); });
}

/* ---------- Explain ---------- */
function renderChat() {
  const box = $('#chat');
  if (!box) return;
  box.innerHTML = chatLog.map(m => {
    if (m.role === 'user') return '<div class="msg u">' + esc(m.content) + '</div>';
    const body = esc(m.content).replace(/\[((?:C\d+\s*,?\s*)+)\]/g, (_, ids) => ids.split(/[\s,]+/).filter(Boolean).map(id => '<span class="tag ret">' + id + '</span>').join(' '));
    return '<div class="msg a">' + body + (m.sources.length ? '<details style="margin-top:.5rem"><summary class="muted">Sources used (' + m.sources.length + ')</summary>' + m.sources.map(s => '<div class="src"><b>' + esc(s.id) + '</b> · ' + esc(s.label) + '<br>' + esc(s.text) + '</div>').join('') + '</details>' : '') + '</div>';
  }).join('');
  box.scrollTop = box.scrollHeight;
}
async function viewExplain() {
  loading();
  const d = await api('/topics');
  $('#view').innerHTML = '<div class="card"><h2>Explain a topic</h2><p class="muted"><span class="tag ret">retrieval</span> pulls the matching passages from your notes; <span class="tag gen">generation</span> may only answer from them. If your notes don\'t cover it, you get "not found", not a guess.</p>' +
    (d.has_notes ? '' : '<p class="bad">Upload notes first.</p>') +
    (d.topics.length ? '<div style="display:flex;gap:.5rem"><select id="tsel" style="margin:0">' + d.topics.map(t => '<option value="' + esc(t.id) + '">' + esc(t.name) + '</option>').join('') + '</select><button id="tgo" class="sec" style="white-space:nowrap">Explain this topic</button></div><div style="height:.75rem"></div>' : '') +
    '<div class="chat" id="chat"></div><div style="display:flex;gap:.5rem"><input id="q" placeholder="Ask about anything in your material" style="margin:0"><button id="ask">Ask</button></div></div>';
  renderChat();
  const send = async q => {
    if (!q.trim()) return;
    const history = chatLog.map(m => ({ role: m.role, content: m.content }));
    chatLog.push({ role: 'user', content: q, sources: [] }); renderChat();
    try {
      const r = await api('/explain', { method: 'POST', body: { question: q, history } });
      chatLog.push({ role: 'assistant', content: r.text, sources: r.sources });
    } catch (e) { chatLog.pop(); toast(e.message, true); }
    renderChat();
  };
  $('#ask').onclick = e => { const q = $('#q').value; $('#q').value = ''; run(e.target, '…', () => send(q)); };
  $('#q').onkeydown = e => { if (e.key === 'Enter') $('#ask').click(); };
  if ($('#tgo')) $('#tgo').onclick = e => run(e.target, '…', () => {
    const t = d.topics.find(x => x.id === $('#tsel').value);
    return send('Explain ' + t.name + ': ' + t.sub.join(', '));
  });
}

/* ---------- Progress ---------- */
function drawChart(cv, vals) {
  const dpr = window.devicePixelRatio || 1, w = cv.clientWidth || 600, h = 220;
  cv.width = w * dpr; cv.height = h * dpr; cv.style.height = h + 'px';
  const g = cv.getContext('2d'); g.scale(dpr, dpr);
  const p = { l: 36, r: 16, t: 14, b: 26 }, iw = w - p.l - p.r, ih = h - p.t - p.b;
  g.font = '11px system-ui'; g.fillStyle = '#697586'; g.strokeStyle = '#e4e9f0'; g.lineWidth = 1;
  [0, 25, 50, 75, 100].forEach(v => { const y = p.t + ih - ih * v / 100; g.beginPath(); g.moveTo(p.l, y); g.lineTo(w - p.r, y); g.stroke(); g.fillText(v, 6, y + 4); });
  const X = i => p.l + (vals.length === 1 ? iw / 2 : iw * i / (vals.length - 1)), Y = v => p.t + ih - ih * v / 100;
  g.strokeStyle = '#315fce'; g.lineWidth = 2.5; g.beginPath();
  vals.forEach((v, i) => { if (i) g.lineTo(X(i), Y(v)); else g.moveTo(X(i), Y(v)); }); g.stroke();
  vals.forEach((v, i) => { g.fillStyle = '#315fce'; g.beginPath(); g.arc(X(i), Y(v), 4, 0, 7); g.fill(); g.fillStyle = '#697586'; g.fillText('#' + (i + 1), X(i) - 8, h - 8); g.fillText(v + '%', X(i) - 10, Y(v) - 9); });
}
async function viewProgress() {
  loading();
  const d = await api('/progress');
  if (!d.attempts.length) { $('#view').innerHTML = '<div class="card"><h2>Progress</h2><p class="muted">No attempts yet. Take a <a href="#quiz">diagnostic quiz</a>.</p></div>'; return; }
  $('#view').innerHTML = '<div class="card"><h2>Progress</h2><canvas id="cv"></canvas></div>' +
    '<div class="card"><h3>Topic mastery</h3>' + d.topics.map(t => {
      const m = t.mastery, dl = t.delta;
      return '<div class="row"><span style="min-width:11rem">' + esc(t.name) + '</span><div style="flex:1;min-width:120px;background:#0f1328;border-radius:99px;height:10px"><div style="width:' + (m == null ? 0 : pct(m)) + '%;height:10px;border-radius:99px;background:' + (m == null ? 'transparent' : m < .5 ? 'var(--bad)' : m < .8 ? 'var(--wa)' : 'var(--ok)') + '"></div></div><span style="min-width:3rem;text-align:right">' + (m == null ? '–' : pct(m) + '%') + '</span><span class="' + (dl > 0 ? 'good' : dl < 0 ? 'bad' : 'muted') + '" style="min-width:3.5rem">' + (dl == null ? '' : (dl > 0 ? '+' : '') + dl + ' pts') + '</span></div>';
    }).join('') + '</div>' +
    '<div class="card"><h3>Attempts</h3><table><tr><th>#</th><th>Date</th><th>Questions</th><th>Score</th></tr>' + d.attempts.map((a, i) => '<tr><td>' + (i + 1) + '</td><td>' + new Date(a.ts).toLocaleString() + '</td><td>' + a.n + '</td><td>' + a.pct + '%</td></tr>').join('') + '</table></div>';
  drawChart($('#cv'), d.attempts.map(a => a.pct));
}

/* ---------- How it works ---------- */
async function viewHow() {
  $('#view').innerHTML = '<div class="card"><h2>Where retrieval and generation are used</h2>' +
    '<p>The Python backend keeps the two apart. <span class="tag ret">Retrieval</span> is BM25 keyword search over your own uploaded passages and decides <i>what the model is allowed to see</i>. <span class="tag gen">Generation</span> is the Groq model, which only receives those passages. Numbers that matter (mastery, levels, priority, minutes) are calculated by code, never by the model.</p>' +
    '<table><tr><th>Feature</th><th>Retrieval (your material)</th><th>Generation (Groq)</th></tr>' +
    '<tr><td>Topic map</td><td>Maps each past-paper question to the closest syllabus topic; checks your notes cover each topic</td><td>Lists topics from the syllabus text</td></tr>' +
    '<tr><td>Diagnostic quiz</td><td>Fetches the top passages for each topic from your notes</td><td>Writes questions using only those passages, with the passage id as citation</td></tr>' +
    '<tr><td>Answer evaluation</td><td>Supplies the cited passage</td><td>Explains why a wrong answer is wrong and grades short answers against the passage. MCQ scoring is plain code</td></tr>' +
    '<tr><td>Gap report</td><td>–</td><td>Writes the "why" from your actual mistakes. Mastery and levels are computed by code</td></tr>' +
    '<tr><td>Revision plan</td><td>Chooses what to re-read; counts past-paper frequency</td><td>Writes short study tips. Priority and schedule are computed by code</td></tr>' +
    '<tr><td>Explain a topic</td><td>Fetches the top 5 passages; if nothing matches, no model call is made</td><td>Answers only from those passages with [C#] citations</td></tr></table></div>' +
    '<div class="card"><h3>How the two are kept separate</h3><ul>' +
    '<li>The model never gets the whole library, only the retrieved passages, each tagged with an id.</li>' +
    '<li>Prompts tell it to use only those passages and to say "Not found in your material" otherwise.</li>' +
    '<li>The server checks every citation: a question is dropped if its cited id was not retrieved, a quote is only shown if it really appears in that passage, and unknown ids are removed from chat answers.</li>' +
    '<li>Quiz answers stay on the server until you submit, so the browser never holds the answer key.</li>' +
    '<li>Past papers shape priorities (what examiners ask) but are never used as a source of answers.</li></ul></div>';
}

/* ---------- Settings ---------- */
async function viewSettings() {
  const me = await api('/me');
  $('#view').innerHTML = (me.temporary_storage ? '<div class="banner">This server is using temporary storage, so accounts and progress will be lost when it restarts. Connect a Postgres database (see README) to keep them.</div>' : '') +
    '<div class="card"><h2>Settings</h2>' +
    '<label>Groq API key<input type="password" id="key" placeholder="gsk_…" value="' + esc(GF.getKey()) + '" autocomplete="off"></label>' +
    '<label>Model<input id="model" list="models" value="' + esc(GF.getModel()) + '"><datalist id="models"><option value="openai/gpt-oss-120b"><option value="qwen/qwen3.6-27b"></datalist></label>' +
    '<p class="muted" style="font-size:.85rem">The key is saved only in this browser and sent with each request so the Python server can call Groq for you. The server does not store it. Use a test key. If a model name stops working, pick another from the Groq console.</p>' +
    '<button id="savekey">Save</button> <button class="sec" id="test">Test connection</button> <span id="tres" class="muted"></span></div>' +
    '<div class="card"><h3>Your data</h3><p class="muted">Material, quizzes and progress for ' + esc(me.email) + ' are saved on the server.</p><button class="sec" id="reset">Delete all my study data</button></div>';
  $('#savekey').onclick = () => { GF.setKey($('#key').value); GF.setModel($('#model').value); toast('Saved.'); };
  $('#test').onclick = e => run(e.target, 'Testing…', async () => {
    GF.setKey($('#key').value); GF.setModel($('#model').value);
    const r = await api('/groq/test', { method: 'POST' });
    $('#tres').innerHTML = '<span class="good">Works: ' + esc(r.reply) + '</span>';
  });
  $('#reset').onclick = e => { if (confirm('Delete all your material, quizzes and progress?')) run(e.target, '…', async () => { await api('/data', { method: 'DELETE' }); chatLog = []; toast('Cleared.'); viewSettings(); }); };
}

/* ---------- init ---------- */
const u = GF.user();
$('#who').textContent = u ? u.name : '';
$('#logout').onclick = () => { GF.logout(); location.href = 'index.html'; };
window.addEventListener('hashchange', render);
render();
})();
