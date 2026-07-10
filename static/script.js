// Voice Email Console - client logic
// Web Speech API for STT/TTS (Chrome/Edge). Talks to Flask for anything
// that needs real inbox/SMTP access.

const $ = (s) => document.querySelector(s);
const micBtn = $('#micBtn');
const micLabel = $('#micLabel');
const statusPill = $('#statusPill');
const statusText = $('#statusText');
const transcript = $('#transcript');
const sttLangSel = $('#sttLang');
const ttsVoiceSel = $('#ttsVoice');
const waveBars = $('#waveBars');

let recognition = null;
let listening = false;
let continuousMode = false;
let lastEmails = [];

// ---------- transcript / status ----------
function log(who, msg, cls = '') {
  const d = document.createElement('div');
  d.className = 't-line ' + cls;
  const w = document.createElement('span');
  w.className = 'who';
  w.textContent = who;
  d.appendChild(w);
  d.appendChild(document.createTextNode(msg));
  transcript.appendChild(d);
  transcript.scrollTop = transcript.scrollHeight;
}
function setStatus(t, mode = '') {
  statusText.textContent = t;
  statusPill.className = 'status-pill ' + mode;
}

// ---------- speech synthesis ----------
function speak(text, rate = 1.0) {
  if (!$('#autoSpeak').checked) return;
  try {
    speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(text);
    const name = ttsVoiceSel.value;
    const voices = speechSynthesis.getVoices();
    const pick = voices.find((v) => v.name === name)
      || voices.find((v) => /en/i.test(v.lang) && /female|zira|samantha|google/i.test(v.name))
      || voices.find((v) => v.lang.startsWith('en'));
    if (pick) u.voice = pick;
    u.rate = rate;
    speechSynthesis.speak(u);
  } catch (e) { /* speechSynthesis not available */ }
}
function loadVoices() {
  const voices = speechSynthesis.getVoices().filter((v) => v.lang.startsWith('en'));
  ttsVoiceSel.innerHTML = '';
  voices.forEach((v) => {
    const o = document.createElement('option');
    o.value = v.name;
    o.textContent = `${v.name} (${v.lang})${v.default ? ' - default' : ''}`;
    ttsVoiceSel.appendChild(o);
  });
  const pref = voices.find((v) => /zira|female|samantha|google.*us/i.test(v.name)) || voices[0];
  if (pref) ttsVoiceSel.value = pref.name;
}
speechSynthesis.onvoiceschanged = loadVoices;
setTimeout(loadVoices, 300);

// ---------- audio-reactive waveform (signature element) ----------
// Independent of SpeechRecognition: opens its own mic stream purely to
// drive the bar meter, so the visual reflects real input level.
let audioCtx = null, analyser = null, waveStream = null, waveRAF = null;
const barEls = () => Array.from(waveBars.children);

async function startWaveform() {
  if (audioCtx) return;
  try {
    waveStream = await navigator.mediaDevices.getUserMedia({ audio: true });
    audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    const src = audioCtx.createMediaStreamSource(waveStream);
    analyser = audioCtx.createAnalyser();
    analyser.fftSize = 64;
    src.connect(analyser);
    waveBars.classList.add('active');
    tickWaveform();
  } catch (e) {
    // mic denied / unavailable - fall back to a gentle idle animation
    idleWaveform();
  }
}
function tickWaveform() {
  if (!analyser) return;
  const data = new Uint8Array(analyser.frequencyBinCount);
  analyser.getByteFrequencyData(data);
  const bars = barEls();
  const step = Math.floor(data.length / bars.length);
  bars.forEach((bar, i) => {
    const v = data[i * step] || 0;
    const h = 6 + Math.round((v / 255) * 28);
    bar.style.height = h + 'px';
  });
  waveRAF = requestAnimationFrame(tickWaveform);
}
function idleWaveform() {
  waveBars.classList.remove('active');
  barEls().forEach((bar, i) => { bar.style.height = (6 + (i % 3) * 2) + 'px'; });
}
function stopWaveform() {
  if (waveRAF) cancelAnimationFrame(waveRAF);
  waveRAF = null;
  if (waveStream) waveStream.getTracks().forEach((t) => t.stop());
  waveStream = null;
  if (audioCtx) { audioCtx.close(); audioCtx = null; }
  analyser = null;
  idleWaveform();
}
idleWaveform();

// ---------- speech recognition ----------
function makeRecognizer(lang) {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) {
    log('SYS', 'Web Speech API not supported - use Chrome or Edge on desktop.', 'err');
    return null;
  }
  const r = new SR();
  r.continuous = false;
  r.interimResults = false;
  r.maxAlternatives = 1;
  r.lang = lang || sttLangSel.value || 'en-IN';
  return r;
}

function startListen(opts = {}) {
  if (listening) return;
  const r = makeRecognizer(opts.lang);
  if (!r) return;
  recognition = r;
  if (opts.continuous) r.continuous = true;

  r.onstart = () => {
    listening = true;
    micBtn.classList.add('listening');
    micBtn.setAttribute('aria-pressed', 'true');
    setStatus('Listening...', 'listening');
    micLabel.textContent = 'Listening...';
    startWaveform();
  };
  r.onend = () => {
    listening = false;
    micBtn.classList.remove('listening');
    micBtn.setAttribute('aria-pressed', 'false');
    setStatus('Ready', 'ready');
    micLabel.textContent = 'Tap mic to start';
    stopWaveform();
    if (continuousMode && opts.rearm !== false) {
      setTimeout(() => startListen(opts), 350);
    }
  };
  r.onerror = (e) => {
    log('SYS', 'Mic error: ' + e.error, 'err');
    setStatus('Mic error', 'err');
  };
  r.onresult = (e) => {
    const text = e.results[0][0].transcript.trim();
    log('YOU', text);
    handleVoiceCommand(text.toLowerCase());
  };
  try { r.start(); } catch (e) { /* already started */ }
}
function stopListen() {
  continuousMode = false;
  try { recognition && recognition.stop(); } catch (e) {}
}

// Multi-turn flows (compose, dictation buttons) need sole control of the
// mic for several one-shot listens in a row. The continuous command loop
// must not try to restart itself in the middle of that, or the two
// recognizers fight over the mic and every prompt looks like it "fails".
function pauseMainLoop() {
  const was = continuousMode;
  continuousMode = false;
  try { recognition && recognition.stop(); } catch (e) {}
  return was;
}
function resumeMainLoopIfNeeded(was) {
  if (was) {
    continuousMode = true;
    setTimeout(() => startListen({ rearm: true }), 300);
  }
}

// ---------- voice command router ----------
function handleVoiceCommand(t) {
  if (/\binbox|mail|read|check|show\b/.test(t) && !/\bread (?:email|message|number)/.test(t)) {
    doInbox();
    return;
  }
  if (/\bcompose|send|write|new mail|email\b/.test(t)) {
    openComposeVoice();
    return;
  }
  const m = t.match(/read (?:email |message |number )?(\d|one|two|three|four|five|six|seven|eight)/);
  if (m || /\bread\b/.test(t)) {
    let idx = 0;
    if (m) {
      const map = { one: 1, two: 2, three: 3, four: 4, five: 5, six: 6, seven: 7, eight: 8 };
      idx = (map[m[1]] || parseInt(m[1]) || 1) - 1;
    }
    readEmailIdx(idx);
    return;
  }
  if (/\bstop|quit|exit|close|goodbye\b/.test(t)) {
    speak('Stopping voice control.');
    log('ASSISTANT', 'Stopping voice control.', 'ai');
    stopListen();
    return;
  }
  if (/\bhelp\b/.test(t)) {
    const help = 'Say inbox to check mail, compose to send an email, read number two to read email two, or stop to stop listening.';
    log('ASSISTANT', help, 'ai');
    speak(help, 0.95);
    return;
  }
  log('ASSISTANT', `Command not recognized: "${t}". Say inbox, compose, or help.`, 'ai');
  speak('Command not recognized. Say inbox, compose, or help.');
}

// ---------- inbox ----------
async function doInbox() {
  setStatus('Loading inbox...', '');
  log('ASSISTANT', 'Checking your inbox...', 'ai');
  speak('Checking your inbox');
  try {
    const unreadOnly = $('#unreadOnly').checked;
    const res = await fetch('/api/inbox', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ limit: 8, unread_only: unreadOnly }),
    });
    const data = await res.json();
    if (!data.ok) {
      log('SYS', data.error || 'Inbox read failed', 'err');
      speak('Sorry, I could not read the inbox.');
      setStatus('Ready', 'ready');
      return;
    }
    lastEmails = data.emails || [];
    renderInbox(lastEmails);
    const n = lastEmails.length;
    const msg = n ? `You have ${n} email${n === 1 ? '' : 's'}.` : 'Your inbox is empty.';
    log('ASSISTANT', msg, 'ai');
    speak(msg);
    if (n > 0) {
      const first = lastEmails[0];
      speak(`First, from ${cleanName(first.from)}. Subject: ${first.subject}. Say read, or read number two for the next one.`);
    }
  } catch (e) {
    log('SYS', 'Inbox failed: ' + e, 'err');
    speak('Inbox read failed');
  }
  setStatus('Ready', 'ready');
}
function renderInbox(list) {
  const box = $('#inboxList');
  if (!list.length) {
    box.innerHTML = '<div class="empty-state">No emails.</div>';
    return;
  }
  box.innerHTML = list.map((m, i) => `
    <div class="email-row" data-i="${i}" tabindex="0" role="button">
      <div>
        <div class="email-from">${esc(m.from.split('<')[0])}</div>
        <div class="email-subj">${esc(m.subject)}</div>
      </div>
      <div class="email-prev">${esc(m.preview || (m.body || '').slice(0, 90))}</div>
    </div>
  `).join('');
  box.querySelectorAll('.email-row').forEach((row) => {
    const open = () => readEmailIdx(parseInt(row.dataset.i, 10));
    row.addEventListener('click', open);
    row.addEventListener('keydown', (e) => { if (e.key === 'Enter') open(); });
  });
}
function cleanName(s) { return (s || '').replace(/<.*?>/g, '').replace(/"/g, '').trim().split(' ')[0] || 'unknown'; }
function esc(s) { const d = document.createElement('div'); d.textContent = s || ''; return d.innerHTML; }

// ---------- read modal ----------
function readEmailIdx(i) {
  const m = lastEmails[i];
  if (!m) { speak('Email not found'); return; }
  $('#readFrom').textContent = 'From: ' + m.from;
  $('#readSubject').textContent = m.subject;
  $('#readBody').textContent = m.body || '(no body)';
  $('#readModal').hidden = false;
  speak(`Email ${i + 1}. From ${cleanName(m.from)}. Subject: ${m.subject}. ${(m.body || '').slice(0, 480)}`, 0.95);
  log('ASSISTANT', `Reading email ${i + 1}`, 'ai');
}
$('#closeModal').onclick = () => { $('#readModal').hidden = true; };
$('#closeRead').onclick = () => { $('#readModal').hidden = true; };
$('#speakAgain').onclick = () => speak($('#readBody').textContent, 0.95);

// ---------- one-shot listen helper ----------
function listenOnce(prompt, seconds = 6, lang = null) {
  return new Promise((resolve) => {
    const r = makeRecognizer(lang);
    if (!r) { resolve(''); return; }
    let done = false;
    const timer = setTimeout(() => {
      try { r.stop(); } catch (e) {}
      if (!done) { done = true; resolve(''); }
    }, seconds * 1000 + 1200);
    r.onresult = (e) => {
      clearTimeout(timer);
      if (done) return;
      done = true;
      const txt = e.results[0][0].transcript;
      log('YOU', txt);
      resolve(txt);
    };
    r.onerror = () => { clearTimeout(timer); if (!done) { done = true; resolve(''); } };
    r.onend = () => { clearTimeout(timer); if (!done) { done = true; resolve(''); } };
    try {
      log('ASSISTANT', prompt, 'ai');
      startWaveform();
      r.start();
    } catch (e) { resolve(''); }
  }).finally(() => stopWaveform());
}

async function askYesNo(promptText) {
  for (let i = 0; i < 3; i++) {
    const ans = await listenOnce(i === 0 ? promptText : 'Please say YES or NO.', 4, 'en-IN');
    if (!ans) continue;
    const r = await fetch('/api/parse_yes_no', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: ans }),
    });
    const j = await r.json();
    if (j.result === true || j.result === false) return j.result;
  }
  return null;
}

// ---------- compose (voice-driven) ----------
async function openComposeVoice() {
  const wasContinuous = pauseMainLoop();
  try {
    log('ASSISTANT', 'Compose mode. Who do you want to send to?', 'ai');
    speak('Who do you want to send to? Say a contact name, or spell the email, saying "at" then "dot com".');

    let to = null;
    for (let attempt = 0; attempt < 3 && !to; attempt++) {
      const spoken = await listenOnce(attempt === 0 ? 'Recipient?' : 'Let\'s try again. Speak slowly.', 12, 'en-IN');
      if (!spoken) { speak("I didn't catch that."); continue; }
      const r = await fetch('/api/parse_email', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: spoken }),
      });
      const j = await r.json();
      if (!j.email) { speak("That didn't sound like a valid email. Let's try again."); continue; }
      speak(`I heard: ${j.spelled || j.email}. Is this correct?`);
      const ok = await askYesNo('Yes or no?');
      if (ok === true) { to = j.email; speak(`Recipient confirmed: ${j.email.split('@')[0]}`); }
      else speak('Okay, cancelled. Trying again.');
    }
    if (!to) { speak('Could not get a valid recipient. Cancelling compose.'); return; }
    $('#toInput').value = to;

    speak('What is the subject?');
    const subject = (await listenOnce('Subject?', 6)) || 'Voice email';
    $('#subjectInput').value = subject;

    speak('Speak your message now.');
    const body = (await listenOnce('Message', 15)) || '(sent by voice email)';
    $('#bodyInput').value = body;

    speak(`Ready to send to ${to.split('@')[0]}. Subject: ${subject}. Say yes to send.`);
    const sendOk = await askYesNo('Say yes to send, or no to cancel.');
    if (sendOk) doSend(to, subject, body);
    else { speak('Email cancelled.'); log('ASSISTANT', 'Compose cancelled.', 'ai'); }
  } finally {
    resumeMainLoopIfNeeded(wasContinuous);
  }
}

// ---------- send ----------
async function doSend(to = null, subject = null, body = null) {
  to = to || $('#toInput').value.trim();
  subject = subject ?? $('#subjectInput').value.trim();
  body = body ?? $('#bodyInput').value.trim();
  if (!to) { $('#sendStatus').textContent = 'A recipient is required.'; return; }
  $('#sendStatus').textContent = 'Sending...';
  try {
    const res = await fetch('/api/send', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ to, subject, body }),
    });
    const j = await res.json();
    $('#sendStatus').textContent = j.message || (j.ok ? 'Sent' : 'Failed');
    if (j.ok) {
      speak('Email sent successfully.');
      log('ASSISTANT', `Email sent to ${j.to || to}`, 'ai');
      $('#composeForm').reset();
    } else {
      speak('Send failed. ' + (j.error || j.message || ''));
      log('SYS', j.error || j.message || 'Send failed', 'err');
    }
  } catch (e) {
    $('#sendStatus').textContent = 'Error: ' + e;
    speak('Send failed.');
  }
}

// ---------- UI wiring ----------
micBtn.onclick = () => {
  if (listening) { stopListen(); return; }
  continuousMode = true;
  startListen({ rearm: true });
};
document.querySelectorAll('.qbtn').forEach((b) => {
  b.onclick = () => {
    const cmd = b.dataset.cmd;
    log('YOU', cmd);
    handleVoiceCommand(cmd);
  };
});
$('#refreshInbox').onclick = doInbox;
$('#sendBtn').onclick = () => doSend();
$('#dictateSubj').onclick = async () => {
  const was = pauseMainLoop();
  const t = await listenOnce('Subject?', 6);
  if (t) $('#subjectInput').value = t;
  resumeMainLoopIfNeeded(was);
};
$('#dictateBody').onclick = async () => {
  const was = pauseMainLoop();
  const t = await listenOnce('Message', 15);
  if (t) $('#bodyInput').value = t;
  resumeMainLoopIfNeeded(was);
};
$('#dictateTo').onclick = async () => {
  const was = pauseMainLoop();
  const t = await listenOnce('Email address - say "at", "dot com"', 12, 'en-IN');
  if (t) {
    const r = await fetch('/api/parse_email', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: t }),
    });
    const j = await r.json();
    $('#toInput').value = (j.email) || t;
  }
  resumeMainLoopIfNeeded(was);
};
$('#contactPick').onchange = (e) => {
  if (e.target.value) $('#toInput').value = e.target.value;
};

// space bar = mic toggle (when not typing in a field)
document.addEventListener('keydown', (e) => {
  if (e.code === 'Space' && e.target.tagName !== 'INPUT' && e.target.tagName !== 'TEXTAREA') {
    e.preventDefault();
    if (listening) stopListen(); else { continuousMode = false; startListen({}); }
  }
});

// ---------- boot ----------
fetch('/api/status').then((r) => r.json()).then((s) => {
  if (s.configured) {
    log('SYS', `Server ready - ${s.email}`, 'ai');
    setStatus('Ready - tap mic', 'ready');
  } else {
    log('SYS', 'Email not configured - copy .env.example to .env and restart.', 'err');
    setStatus('Not configured', 'err');
  }
}).catch(() => {
  log('SYS', 'Could not reach the server.', 'err');
});
setStatus('Idle', '');
setTimeout(() => {
  const msg = 'Voice email ready. Say inbox, or compose, or tap the buttons below.';
  log('ASSISTANT', msg, 'ai');
  if ($('#autoSpeak').checked) speak(msg, 0.95);
}, 700);