/* English Tutor — single-page app (no build step). */
'use strict';

// ------------------------------------------------------------------ helpers

function h(tag, attrs, ...children) {
  const el = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs || {})) {
    if (value == null || value === false) continue;
    if (key === 'class') el.className = value;
    else if (key === 'html') el.innerHTML = value; // only for trusted server-rendered HTML
    else if (key.startsWith('on')) el.addEventListener(key.slice(2).toLowerCase(), value);
    else if (value === true) el.setAttribute(key, '');
    else el.setAttribute(key, value);
  }
  for (const child of children.flat(Infinity)) {
    if (child == null || child === false) continue;
    el.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return el;
}

async function api(path, body) {
  const options = body === undefined ? {} : {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  };
  const res = await fetch('/api' + path, options);
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.detail || `Ошибка сервера (${res.status})`);
  }
  return res.json();
}

function toast(message, kind = 'info') {
  const box = h('div', { class: `toast ${kind}` }, message);
  document.getElementById('toasts').append(box);
  setTimeout(() => box.classList.add('hide'), 4500);
  setTimeout(() => box.remove(), 5000);
}

function shuffle(list) {
  const a = list.slice();
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [a[i], a[j]] = [a[j], a[i]];
  }
  return a;
}

function pct(correct, total) {
  return total ? Math.round((100 * correct) / total) : 0;
}

function plural(n, one, few, many) {
  const mod10 = n % 10, mod100 = n % 100;
  if (mod10 === 1 && mod100 !== 11) return one;
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return few;
  return many;
}

/** Render a question text, highlighting "___" blanks. */
function questionText(text) {
  const parts = text.split(/_{2,}/);
  const nodes = [];
  parts.forEach((part, i) => {
    nodes.push(part);
    if (i < parts.length - 1) nodes.push(h('span', { class: 'blank' }, '____'));
  });
  return nodes;
}

function levelBadge(level) {
  return h('span', { class: `badge level-${String(level).slice(0, 2)}` }, level);
}

function storageGet(key, fallback) {
  try {
    const raw = localStorage.getItem(key);
    return raw ? JSON.parse(raw) : fallback;
  } catch (e) {
    return fallback;
  }
}

function storageSet(key, value) {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch (e) { /* private mode — progress just isn't saved */ }
}

// ----------------------------------------------------------------- settings

const Settings = {
  defaults: { voice: '', rate: 0.95, tts: 'auto', stt: 'auto', autoplay: true, showRu: true },
  get() {
    return { ...this.defaults, ...storageGet('et-settings', {}) };
  },
  set(patch) {
    storageSet('et-settings', { ...this.get(), ...patch });
  },
};

// ----------------------------------------------------------------- progress

const Progress = {
  key: 'et-progress-v1',
  load() {
    return storageGet(this.key, { results: {}, days: [] });
  },
  /** kind: test | grammar | dictation | listening | speaking | answer | dialogue */
  record(kind, ref, correct, total) {
    const data = this.load();
    const id = `${kind}:${ref}`;
    const percent = pct(correct, total);
    const prev = data.results[id] || { best: 0, attempts: 0 };
    data.results[id] = {
      kind, ref, last: percent, best: Math.max(prev.best, percent),
      attempts: prev.attempts + 1, at: new Date().toISOString(),
    };
    const today = new Date().toISOString().slice(0, 10);
    if (!data.days.includes(today)) data.days.push(today);
    storageSet(this.key, data);
  },
  get(kind, ref) {
    return this.load().results[`${kind}:${ref}`] || null;
  },
  byKind(kind) {
    return Object.values(this.load().results).filter(r => r.kind === kind);
  },
  streak() {
    const days = new Set(this.load().days);
    let streak = 0;
    const d = new Date();
    if (!days.has(d.toISOString().slice(0, 10))) d.setDate(d.getDate() - 1);
    while (days.has(d.toISOString().slice(0, 10))) {
      streak++;
      d.setDate(d.getDate() - 1);
    }
    return streak;
  },
  reset() {
    storageSet(this.key, { results: {}, days: [] });
  },
};

// ------------------------------------------------------------ text-to-speech

const Voice = {
  voices: [],
  audio: null,
  resolve: null,

  init() {
    if (!('speechSynthesis' in window)) return;
    const load = () => {
      this.voices = speechSynthesis.getVoices().filter(v => /^en([-_]|$)/i.test(v.lang));
    };
    load();
    speechSynthesis.addEventListener('voiceschanged', load);
  },

  pick() {
    const wanted = Settings.get().voice;
    const byPref = wanted && this.voices.find(v => v.voiceURI === wanted);
    return byPref
      || this.voices.find(v => /en[-_]US/i.test(v.lang) && v.localService)
      || this.voices.find(v => /en[-_]US/i.test(v.lang))
      || this.voices.find(v => /en[-_]GB/i.test(v.lang))
      || this.voices[0];
  },

  useBrowser() {
    const mode = Settings.get().tts;
    if (mode === 'server') return false;
    return 'speechSynthesis' in window && this.voices.length > 0;
  },

  stop() {
    if ('speechSynthesis' in window) speechSynthesis.cancel();
    if (this.audio) {
      this.audio.pause();
      this.audio = null;
    }
    if (this.resolve) this.resolve();
    this.resolve = null;
  },

  speak(text, { slow = false } = {}) {
    this.stop();
    return this.useBrowser() ? this.browser(text, slow) : this.server(text, slow);
  },

  browser(text, slow) {
    const voice = this.pick();
    const rate = slow ? 0.6 : Number(Settings.get().rate) || 1;
    // Long utterances get cut off in some browsers — speak sentence by sentence.
    const parts = (text.match(/[^.!?]+[.!?]*["”]?\s*/g) || [text]).map(p => p.trim()).filter(Boolean);
    return new Promise(resolve => {
      this.resolve = resolve;
      parts.forEach((part, index) => {
        const u = new SpeechSynthesisUtterance(part);
        u.lang = voice ? voice.lang : 'en-US';
        if (voice) u.voice = voice;
        u.rate = rate;
        if (index === parts.length - 1) {
          u.onend = () => resolve();
          u.onerror = () => resolve();
        }
        speechSynthesis.speak(u);
      });
    });
  },

  server(text, slow) {
    return new Promise(resolve => {
      const audio = new Audio(`/api/tts?text=${encodeURIComponent(text)}&slow=${slow ? 'true' : 'false'}`);
      if (!slow) audio.playbackRate = Number(Settings.get().rate) || 1;
      this.audio = audio;
      this.resolve = resolve;
      audio.onended = () => resolve();
      audio.onerror = () => {
        toast('Не удалось воспроизвести озвучку. Проверьте интернет или выберите голос браузера в настройках.', 'error');
        resolve();
      };
      audio.play().catch(() => resolve());
    });
  },
};

function SpeakButtons(getText, { label = '🔊 Слушать', slowLabel = '🐢 Медленно', compact = false } = {}) {
  const cls = compact ? 'btn small ghost' : 'btn secondary';
  return h('span', { class: 'speak-buttons' },
    h('button', { class: cls, type: 'button', onclick: () => Voice.speak(getText()) }, label),
    slowLabel && h('button', { class: cls, type: 'button', onclick: () => Voice.speak(getText(), { slow: true }) }, slowLabel),
  );
}

function SpeakIcon(text) {
  return h('button', { class: 'icon-btn', type: 'button', title: 'Прослушать', 'aria-label': 'Прослушать', onclick: () => Voice.speak(text) }, '🔊');
}

// ------------------------------------------------------------ speech-to-text

class MicError extends Error {
  constructor(code, detail) {
    super(detail || code);
    this.code = code;
  }
}

const Mic = {
  current: null,
  forceServer: false,

  browserSupported() {
    return Boolean(window.SpeechRecognition || window.webkitSpeechRecognition);
  },
  recorderSupported() {
    return Boolean(navigator.mediaDevices && navigator.mediaDevices.getUserMedia && window.MediaRecorder);
  },
  supported() {
    return this.browserSupported() || this.recorderSupported();
  },
  engine() {
    const mode = this.forceServer ? 'server' : Settings.get().stt;
    const browser = this.browserSupported(), server = this.recorderSupported();
    if (mode === 'server') return server ? 'server' : (browser ? 'browser' : null);
    return browser ? 'browser' : (server ? 'server' : null);
  },

  abort() {
    if (this.current) this.current.abort();
    this.current = null;
  },

  async start(options = {}) {
    this.abort();
    const engine = this.engine();
    if (!engine) throw new MicError('unsupported');
    const session = engine === 'browser' ? this.browserSession(options) : await this.serverSession(options);
    this.current = session;
    session.result.finally(() => {
      if (this.current === session) this.current = null;
    }).catch(() => {});
    return session;
  },

  browserSession({ continuous = false, onInterim }) {
    const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    const rec = new Recognition();
    rec.lang = 'en-US';
    rec.interimResults = true;
    rec.continuous = continuous;
    rec.maxAlternatives = 1;
    let finalText = '', interim = '', aborted = false;
    const result = new Promise((resolve, reject) => {
      rec.onresult = event => {
        interim = '';
        for (let i = event.resultIndex; i < event.results.length; i++) {
          const r = event.results[i];
          if (r.isFinal) finalText += r[0].transcript + ' ';
          else interim += r[0].transcript;
        }
        if (onInterim) onInterim((finalText + interim).trim());
      };
      rec.onerror = event => {
        if (event.error === 'no-speech' || event.error === 'aborted') return;
        if (event.error === 'network' || event.error === 'service-not-allowed' || event.error === 'language-not-supported') {
          if (this.recorderSupported()) this.forceServer = true;
        }
        reject(new MicError(event.error));
      };
      rec.onend = () => resolve(aborted ? null : (finalText + interim).trim());
    });
    rec.start();
    return {
      stop: () => rec.stop(),
      abort: () => { aborted = true; rec.abort(); },
      result,
    };
  },

  async serverSession({ onInterim, maxSeconds = 60 }) {
    let stream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (e) {
      throw new MicError('not-allowed');
    }
    const types = ['audio/webm;codecs=opus', 'audio/ogg;codecs=opus', 'audio/mp4', 'audio/webm'];
    const mimeType = types.find(t => MediaRecorder.isTypeSupported && MediaRecorder.isTypeSupported(t));
    const rec = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
    const chunks = [];
    let aborted = false;
    rec.ondataavailable = e => { if (e.data && e.data.size) chunks.push(e.data); };
    const stopped = new Promise(resolve => { rec.onstop = resolve; });
    rec.start();
    if (onInterim) onInterim('🎙 Идёт запись… Нажмите «Готово», когда закончите.');
    const timer = setTimeout(() => { if (rec.state !== 'inactive') rec.stop(); }, maxSeconds * 1000);
    const result = stopped.then(async () => {
      clearTimeout(timer);
      stream.getTracks().forEach(t => t.stop());
      if (aborted) return null;
      if (onInterim) onInterim('⏳ Распознаю речь…');
      const type = rec.mimeType || mimeType || 'audio/webm';
      const ext = type.includes('ogg') ? 'ogg' : type.includes('mp4') ? 'm4a' : 'webm';
      const form = new FormData();
      form.append('audio', new Blob(chunks, { type }), `speech.${ext}`);
      const res = await fetch('/api/stt', { method: 'POST', body: form });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new MicError('server', data.detail);
      return data.text || '';
    });
    return {
      stop: () => { if (rec.state !== 'inactive') rec.stop(); },
      abort: () => { aborted = true; if (rec.state !== 'inactive') rec.stop(); },
      result,
    };
  },
};

function micErrorText(error) {
  const code = error && error.code;
  if (code === 'unsupported') return 'Ваш браузер не поддерживает запись голоса. Попробуйте Chrome, Edge или Safari.';
  if (code === 'not-allowed' || (code === 'service-not-allowed' && !Mic.recorderSupported())) {
    return 'Нет доступа к микрофону. Разрешите его в настройках браузера.';
  }
  if (code === 'network' || code === 'service-not-allowed') {
    return 'Распознавание в браузере недоступно. Переключился на серверное — попробуйте ещё раз.';
  }
  if (code === 'audio-capture') return 'Микрофон не найден.';
  if (code === 'server') return error.message || 'Сервер не смог распознать речь.';
  return 'Ошибка распознавания речи: ' + (error && error.message ? error.message : 'неизвестная ошибка');
}

/** A record button. Calls onResult(text) with the recognized text. */
function MicButton({ onResult, continuous = false, label = '🎤 Говорить' }) {
  const button = h('button', { class: 'btn mic', type: 'button' }, label);
  const live = h('div', { class: 'live' });
  let session = null;
  button.addEventListener('click', async () => {
    if (session) {
      session.stop();
      button.disabled = true;
      button.classList.remove('recording');
      button.textContent = '⏳ Обработка…';
      return;
    }
    Voice.stop();
    try {
      session = await Mic.start({ continuous, onInterim: text => { live.textContent = text; } });
    } catch (e) {
      toast(micErrorText(e), 'error');
      return;
    }
    button.classList.add('recording');
    button.textContent = '⏹ Готово';
    live.textContent = 'Говорите по-английски…';
    try {
      const text = await session.result;
      live.textContent = '';
      if (text !== null) onResult(text);
    } catch (e) {
      live.textContent = '';
      toast(micErrorText(e), 'error');
    } finally {
      session = null;
      button.disabled = false;
      button.classList.remove('recording');
      button.textContent = label;
    }
  });
  return h('div', { class: 'mic-wrap' }, button, live);
}

/** Render word-by-word comparison returned by the API. */
function ComparisonView(result, { heardLabel = 'Распознано' } = {}) {
  const cls = result.score >= 80 ? 'good' : result.score >= 50 ? 'ok' : 'bad';
  return h('div', { class: `comparison ${cls}` },
    h('div', { class: 'score-row' },
      h('div', { class: `score-circle ${cls}` }, `${result.score}%`),
      h('div', {},
        h('div', { class: 'verdict' }, result.verdict),
        h('div', { class: 'muted' }, `${heardLabel}: `, h('i', {}, result.heard || '—')),
      ),
    ),
    h('div', { class: 'marked' }, result.marks.map(m => h('span', { class: m.ok ? 'w ok' : 'w miss' }, m.word))),
    result.missing.length ? h('div', { class: 'muted small' }, 'Пропущено или с ошибкой: ', result.missing.join(', ')) : null,
  );
}

// ---------------------------------------------------------------- quiz view

/**
 * Generic quiz used by tests, grammar practice and listening comprehension.
 * check(question, answer) must resolve to {correct, correct_answer, explanation}.
 */
function Quiz({ questions, check, onFinish, backHref, backLabel }) {
  const root = h('div', { class: 'quiz' });
  let index = 0, correct = 0, mistakes = [];

  function showQuestion() {
    const q = questions[index];
    const progress = h('div', { class: 'progress' },
      h('div', { class: 'progress-bar', style: `width:${pct(index, questions.length)}%` }));
    const feedback = h('div', { class: 'feedback' });
    const next = h('button', { class: 'btn primary hidden', type: 'button' },
      index === questions.length - 1 ? 'Результат →' : 'Далее →');
    next.addEventListener('click', () => {
      index++;
      if (index < questions.length) showQuestion(); else finish();
    });

    let answered = false;
    async function submit(answer, onResult) {
      if (answered) return;
      answered = true;
      let res;
      try {
        res = await check(q, answer);
      } catch (e) {
        answered = false;
        toast(e.message, 'error');
        return;
      }
      if (res.correct) correct++;
      else mistakes.push({ question: q.question, given: res.given, correct: res.correct_answer });
      onResult(res);
      feedback.replaceChildren(
        h('div', { class: res.correct ? 'fb good' : 'fb bad' },
          h('b', {}, res.correct ? '✅ Верно!' : '❌ Неверно.'),
          res.correct ? null : h('span', {}, ' Правильный ответ: ', h('b', {}, res.correct_answer)),
          res.explanation ? h('div', { class: 'explanation' }, res.explanation) : null,
        ),
      );
      next.classList.remove('hidden');
      next.focus();
    }

    let body;
    if (q.type === 'choice') {
      const buttons = q.options.map((option, i) => h('button', {
        class: 'option', type: 'button',
        onclick: () => submit(i, res => {
          buttons.forEach((b, j) => {
            b.disabled = true;
            if (q.options[j] === res.correct_answer) b.classList.add('correct');
          });
          if (!res.correct) buttons[i].classList.add('wrong');
        }),
      }, option));
      body = h('div', { class: 'options' }, buttons);
    } else {
      const input = h('input', { class: 'text-input', type: 'text', placeholder: 'Ваш ответ…', autocomplete: 'off', autocapitalize: 'off', spellcheck: 'false' });
      const go = h('button', { class: 'btn primary', type: 'submit' }, 'Проверить');
      body = h('form', {
        class: 'input-row',
        onsubmit: e => {
          e.preventDefault();
          if (!input.value.trim()) { input.focus(); return; }
          submit(input.value, res => {
            input.disabled = true;
            go.disabled = true;
            input.classList.add(res.correct ? 'correct' : 'wrong');
          });
        },
      }, input, go);
      setTimeout(() => input.focus(), 0);
    }

    root.replaceChildren(
      progress,
      h('div', { class: 'muted small' }, `Вопрос ${index + 1} из ${questions.length}`),
      h('div', { class: 'question' }, questionText(q.question)),
      body,
      feedback,
      h('div', { class: 'actions' }, next),
    );
  }

  function finish() {
    const percent = pct(correct, questions.length);
    const extra = onFinish ? onFinish({ correct, total: questions.length, percent }) : null;
    const emoji = percent >= 90 ? '🏆' : percent >= 70 ? '🎉' : percent >= 50 ? '👍' : '💪';
    root.replaceChildren(
      h('div', { class: 'result' },
        h('div', { class: 'result-emoji' }, emoji),
        h('h2', {}, `${correct} из ${questions.length} (${percent}%)`),
        h('p', { class: 'muted' }, percent >= 70 ? 'Отличная работа!' : 'Повторите теорию и попробуйте ещё раз.'),
        extra,
        mistakes.length ? h('div', { class: 'mistakes' },
          h('h3', {}, 'Работа над ошибками'),
          mistakes.map(m => h('div', { class: 'mistake' },
            h('div', {}, questionText(m.question)),
            h('div', { class: 'small' }, 'Ваш ответ: ', h('s', {}, m.given || '—'), ' → ', h('b', {}, m.correct)),
          )),
        ) : null,
        h('div', { class: 'actions center' },
          h('button', {
            class: 'btn primary', type: 'button',
            onclick: () => { index = 0; correct = 0; mistakes = []; showQuestion(); },
          }, '🔁 Пройти ещё раз'),
          backHref ? h('a', { class: 'btn secondary', href: backHref }, backLabel || '← Назад') : null,
        ),
      ),
    );
  }

  showQuestion();
  return root;
}

// -------------------------------------------------------------------- pages

let overviewCache = null;

async function pageHome() {
  const overview = overviewCache || (overviewCache = await api('/overview'));
  const tests = Progress.byKind('test');
  const lessons = Progress.byKind('grammar').filter(r => r.best >= 70);
  const speaking = Progress.byKind('speaking');
  const avgSpeaking = speaking.length ? Math.round(speaking.reduce((s, r) => s + r.best, 0) / speaking.length) : null;

  const card = (href, icon, title, text, meta) => h('a', { class: 'card feature', href },
    h('div', { class: 'feature-icon' }, icon),
    h('h3', {}, title),
    h('p', {}, text),
    meta ? h('div', { class: 'muted small' }, meta) : null,
  );

  return h('div', {},
    h('section', { class: 'hero' },
      h('h1', {}, 'Английский самостоятельно — каждый день'),
      h('p', {}, 'Тесты, грамматика с упражнениями, аудирование и разговорная практика с распознаванием речи. Всё бесплатно и прямо в браузере.'),
      h('div', { class: 'actions' },
        h('a', { class: 'btn primary', href: '#/tests/placement' }, '🎯 Тест на уровень'),
        h('a', { class: 'btn secondary', href: '#/grammar' }, '📘 Начать с грамматики'),
      ),
    ),
    h('section', { class: 'stats' },
      stat('🔥', Progress.streak(), plural(Progress.streak(), 'день подряд', 'дня подряд', 'дней подряд')),
      stat('📝', tests.length, 'тестов пройдено'),
      stat('📘', `${lessons.length}/${overview.grammar}`, 'тем изучено'),
      stat('🗣', avgSpeaking === null ? '—' : `${avgSpeaking}%`, 'точность произношения'),
    ),
    h('section', { class: 'grid' },
      card('#/tests', '📝', 'Тесты', 'Проверьте уровень, лексику, времена, предлоги и фразовые глаголы.', `${overview.tests} тестов`),
      card('#/grammar', '📘', 'Грамматика', 'Понятные объяснения на русском, примеры с озвучкой и упражнения.', `${overview.grammar} тем от A1 до B2`),
      card('#/listening', '🎧', 'Аудирование', 'Диктанты и тексты с вопросами. Можно замедлить речь.', `${overview.dictation} фраз · ${overview.comprehension} текстов`),
      card('#/speaking', '🗣', 'Говорение', 'Повторяйте фразы вслух — сайт распознает речь и оценит произношение.', `${overview.phrases} фраз · ${overview.speaking_questions} вопросов`),
      card('#/dialogues', '💬', 'Диалоги', 'Ролевые диалоги голосом: кафе, отель, врач, собеседование.', `${overview.dialogues} ситуаций`),
      overview.bot_url
        ? h('a', { class: 'card feature', href: overview.bot_url, target: '_blank', rel: 'noopener' },
          h('div', { class: 'feature-icon' }, '🤖'), h('h3', {}, 'Telegram-бот'),
          h('p', {}, 'Те же упражнения в Telegram: тесты, грамматика, голосовые сообщения.'))
        : card('#/progress', '📊', 'Прогресс', 'Статистика занятий, серия дней и настройки голоса.', null),
    ),
    Mic.supported() ? null : h('div', { class: 'notice' },
      '⚠️ Ваш браузер не поддерживает запись голоса — разделы «Говорение» и «Диалоги» будут работать только в текстовом режиме. Рекомендуем Chrome или Edge.'),
  );
}

function stat(icon, value, label) {
  return h('div', { class: 'stat' }, h('div', { class: 'stat-value' }, icon, ' ', String(value)), h('div', { class: 'stat-label' }, label));
}

// tests

async function pageTests() {
  const tests = await api('/tests');
  return h('div', {},
    h('h1', {}, '📝 Тесты'),
    h('p', { class: 'muted' }, 'Начните с теста на уровень, чтобы понять, какие темы повторить.'),
    h('div', { class: 'grid' }, tests.map(t => {
      const result = Progress.get('test', t.id);
      return h('a', { class: 'card', href: `#/tests/${t.id}` },
        h('div', { class: 'card-top' }, levelBadge(t.level), result ? h('span', { class: 'best' }, `лучший: ${result.best}%`) : null),
        h('h3', {}, t.title),
        h('p', {}, t.description),
        h('div', { class: 'muted small' }, `${t.questions} ${plural(t.questions, 'вопрос', 'вопроса', 'вопросов')}`),
      );
    })),
  );
}

async function pageTest(id) {
  const test = await api(`/tests/${id}`);
  return h('div', { class: 'narrow' },
    h('a', { class: 'crumb', href: '#/tests' }, '← Все тесты'),
    h('h1', {}, test.title, ' ', levelBadge(test.level)),
    h('p', { class: 'muted' }, test.description),
    h('div', { class: 'card' }, Quiz({
      questions: test.questions,
      check: (q, answer) => api(`/tests/${id}/check`, { question_id: q.id, answer }),
      backHref: '#/tests',
      backLabel: '← К тестам',
      onFinish: ({ correct, total }) => {
        Progress.record('test', id, correct, total);
        if (!test.grading.length) return null;
        let level = null;
        for (const [min, name] of test.grading) if (correct >= min) level = name;
        return h('div', { class: 'level-result' }, 'Ваш примерный уровень: ', levelBadge(level));
      },
    })),
  );
}

// grammar

async function pageGrammar() {
  const lessons = await api('/grammar');
  const levels = [...new Set(lessons.map(l => l.level))];
  return h('div', {},
    h('h1', {}, '📘 Грамматика'),
    h('p', { class: 'muted' }, 'Прочитайте объяснение, послушайте примеры и закрепите тему упражнениями. Тема считается изученной при результате от 70%.'),
    levels.map(level => h('section', {},
      h('h2', { class: 'level-title' }, levelBadge(level), ' Уровень ', level),
      h('div', { class: 'grid' }, lessons.filter(l => l.level === level).map(l => {
        const result = Progress.get('grammar', l.id);
        const done = result && result.best >= 70;
        return h('a', { class: `card${done ? ' done' : ''}`, href: `#/grammar/${l.id}` },
          h('div', { class: 'card-top' }, h('span', { class: 'muted small' }, l.title_ru), done ? h('span', { class: 'best' }, `✓ ${result.best}%`) : null),
          h('h3', {}, l.title),
          h('p', {}, l.summary),
        );
      })),
    )),
  );
}

async function pageLesson(id) {
  const lesson = await api(`/grammar/${id}`);
  const practice = h('div', { class: 'card' });
  const startPractice = () => practice.replaceChildren(Quiz({
    questions: lesson.exercises,
    check: (q, answer) => api(`/grammar/${id}/check`, { question_id: q.id, answer }),
    backHref: '#/grammar',
    backLabel: '← К темам',
    onFinish: ({ correct, total, percent }) => {
      Progress.record('grammar', id, correct, total);
      return percent >= 70 ? h('div', { class: 'level-result' }, '✓ Тема изучена!') : null;
    },
  }));
  practice.append(
    h('p', {}, `${lesson.exercises.length} упражнений по теме «${lesson.title}».`),
    h('button', { class: 'btn primary', type: 'button', onclick: startPractice }, '✍️ Начать практику'),
  );
  const allExamples = lesson.examples.map(e => e.en).join(' ');
  return h('div', { class: 'narrow' },
    h('a', { class: 'crumb', href: '#/grammar' }, '← Все темы'),
    h('h1', {}, lesson.title, ' ', levelBadge(lesson.level)),
    h('p', { class: 'muted' }, lesson.title_ru, ' · ', lesson.summary),
    h('article', { class: 'card theory', html: lesson.theory_html }),
    h('section', { class: 'card' },
      h('div', { class: 'section-head' }, h('h2', {}, 'Примеры'), SpeakButtons(() => allExamples, { label: '🔊 Все примеры', slowLabel: null, compact: true })),
      h('ul', { class: 'examples' }, lesson.examples.map(e => h('li', {},
        SpeakIcon(e.en), h('div', {}, h('div', { class: 'en' }, e.en), h('div', { class: 'ru' }, e.ru)),
      ))),
    ),
    h('h2', {}, 'Практика'),
    practice,
  );
}

// listening

let listeningCache = null;

async function pageListening() {
  const data = listeningCache || (listeningCache = await api('/listening'));
  const tab = storageGet('et-listening-tab', 'dictation');
  const body = h('div', {});
  const tabs = Tabs([
    ['dictation', '✍️ Диктант', () => Dictation(data.dictation)],
    ['texts', '🎧 Тексты с вопросами', () => ListeningTexts(data.comprehension)],
  ], tab, key => storageSet('et-listening-tab', key), body);
  return h('div', { class: 'narrow' },
    h('h1', {}, '🎧 Аудирование'),
    h('p', { class: 'muted' }, 'Слушайте английскую речь и тренируйте понимание на слух.'),
    tabs, body,
  );
}

function Tabs(items, active, onChange, body) {
  const buttons = items.map(([key, label, render]) => {
    const b = h('button', { class: 'tab', type: 'button', role: 'tab' }, label);
    b.addEventListener('click', () => select(key));
    b.dataset.key = key;
    return b;
  });
  function select(key) {
    Voice.stop();
    Mic.abort();
    const item = items.find(i => i[0] === key) || items[0];
    buttons.forEach(b => b.classList.toggle('active', b.dataset.key === item[0]));
    body.replaceChildren(item[2]());
    onChange(item[0]);
  }
  select(active);
  return h('div', { class: 'tabs', role: 'tablist' }, buttons);
}

function LevelChips(levels, active, onSelect) {
  const chips = levels.map(level => {
    const chip = h('button', { class: 'chip', type: 'button' }, level === 'all' ? 'Все' : level);
    chip.addEventListener('click', () => {
      chips.forEach(c => c.classList.remove('active'));
      chip.classList.add('active');
      onSelect(level);
    });
    if (level === active) chip.classList.add('active');
    return chip;
  });
  return h('div', { class: 'chips' }, chips);
}

function Dictation(items) {
  const levels = ['A1', 'A2', 'B1', 'B2'];
  let level = storageGet('et-dictation-level', 'A1');
  let queue = [], position = 0;
  const area = h('div', {});

  function start(newLevel) {
    level = newLevel;
    storageSet('et-dictation-level', level);
    queue = shuffle(items.filter(i => i.level === level));
    position = 0;
    show();
  }

  function show() {
    if (position >= queue.length) {
      queue = shuffle(queue);
      position = 0;
    }
    const item = queue[position];
    const input = h('textarea', { class: 'text-input', rows: '2', placeholder: 'Напишите, что услышали…', spellcheck: 'false', autocapitalize: 'off' });
    const result = h('div', {});
    const check = h('button', { class: 'btn primary', type: 'button' }, 'Проверить');
    const next = h('button', { class: 'btn secondary', type: 'button', onclick: () => { position++; show(); } }, 'Следующая фраза →');
    check.addEventListener('click', async () => {
      if (!input.value.trim()) { input.focus(); return; }
      try {
        const res = await api(`/listening/dictation/${item.id}/check`, { answer: input.value });
        Progress.record('dictation', item.id, res.score, 100);
        result.replaceChildren(
          ComparisonView(res, { heardLabel: 'Вы написали' }),
          h('div', { class: 'translation' }, '🇷🇺 ', res.ru),
        );
        check.disabled = true;
        next.focus();
      } catch (e) {
        toast(e.message, 'error');
      }
    });
    input.addEventListener('keydown', e => {
      if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); check.click(); }
    });
    area.replaceChildren(h('div', { class: 'card' },
      h('div', { class: 'muted small' }, `Уровень ${level} · фраза ${position + 1} из ${queue.length}`),
      h('p', {}, 'Прослушайте фразу (можно несколько раз) и напишите её по-английски.'),
      h('div', { class: 'actions' }, SpeakButtons(() => item.text, { label: '▶ Слушать' })),
      input,
      h('div', { class: 'actions' }, check, next),
      result,
    ));
    Voice.speak(item.text);
  }

  const wrap = h('div', {}, LevelChips(levels, level, start), area);
  start(level);
  return wrap;
}

function ListeningTexts(items) {
  return h('div', { class: 'grid' }, items.map(item => {
    const result = Progress.get('listening', item.id);
    return h('a', { class: 'card', href: `#/listening/${item.id}` },
      h('div', { class: 'card-top' }, levelBadge(item.level), result ? h('span', { class: 'best' }, `лучший: ${result.best}%`) : null),
      h('h3', {}, item.title),
      h('p', {}, item.title_ru),
      h('div', { class: 'muted small' }, `${item.questions.length} ${plural(item.questions.length, 'вопрос', 'вопроса', 'вопросов')}`),
    );
  }));
}

async function pageListeningText(id) {
  const data = listeningCache || (listeningCache = await api('/listening'));
  const item = data.comprehension.find(i => i.id === id);
  if (!item) throw new Error('Текст не найден');
  const transcript = h('div', { class: 'transcript hidden' }, item.text);
  const toggle = h('button', {
    class: 'btn small ghost', type: 'button',
    onclick: () => {
      transcript.classList.toggle('hidden');
      toggle.textContent = transcript.classList.contains('hidden') ? '📄 Показать текст' : '🙈 Скрыть текст';
    },
  }, '📄 Показать текст');
  return h('div', { class: 'narrow' },
    h('a', { class: 'crumb', href: '#/listening' }, '← Аудирование'),
    h('h1', {}, item.title, ' ', levelBadge(item.level)),
    h('p', { class: 'muted' }, item.title_ru, '. Прослушайте текст, затем ответьте на вопросы. Текст можно включать сколько угодно раз.'),
    h('div', { class: 'card player' },
      h('div', { class: 'actions' }, SpeakButtons(() => item.text, { label: '▶ Слушать текст' }),
        h('button', { class: 'btn secondary', type: 'button', onclick: () => Voice.stop() }, '⏹ Стоп')),
      toggle, transcript,
    ),
    h('div', { class: 'card' }, Quiz({
      questions: item.questions,
      check: (q, answer) => api(`/listening/comprehension/${id}/check`, { question_id: q.id, answer }),
      backHref: '#/listening',
      backLabel: '← К аудированию',
      onFinish: ({ correct, total }) => {
        Progress.record('listening', id, correct, total);
        transcript.classList.remove('hidden');
        toggle.textContent = '🙈 Скрыть текст';
        return null;
      },
    })),
  );
}

// speaking

let speakingCache = null;

async function pageSpeaking() {
  const data = speakingCache || (speakingCache = await api('/speaking'));
  const body = h('div', {});
  const tabs = Tabs([
    ['repeat', '🔁 Повторяй за мной', () => RepeatPractice(data)],
    ['questions', '❓ Ответь на вопрос', () => QuestionPractice(data.questions)],
    ['free', '🎙 Свободная речь', () => FreeSpeech()],
  ], storageGet('et-speaking-tab', 'repeat'), key => storageSet('et-speaking-tab', key), body);
  return h('div', { class: 'narrow' },
    h('h1', {}, '🗣 Говорение'),
    h('p', { class: 'muted' }, 'Говорите вслух: сайт распознает вашу речь и покажет, какие слова прозвучали правильно.'),
    Mic.supported() ? null : h('div', { class: 'notice' }, '⚠️ Браузер не поддерживает запись голоса. Попробуйте Chrome, Edge или Safari.'),
    tabs, body,
  );
}

function RepeatPractice(data) {
  const topics = Object.keys(data.topics);
  let topic = storageGet('et-speaking-topic', topics[0]);
  if (!data.topics[topic]) topic = topics[0];
  let queue = [], position = 0;
  let hideText = false;
  const area = h('div', {});

  const select = h('select', { class: 'select' }, topics.map(t => h('option', { value: t }, data.topics[t])));
  select.value = topic;
  select.addEventListener('change', () => start(select.value));

  function start(newTopic) {
    topic = newTopic;
    storageSet('et-speaking-topic', topic);
    queue = shuffle(data.phrases.filter(p => p.topic === topic));
    position = 0;
    show();
  }

  function show() {
    if (position >= queue.length) { queue = shuffle(queue); position = 0; }
    const phrase = queue[position];
    const result = h('div', {});
    const text = h('div', { class: `phrase${hideText ? ' blurred' : ''}` }, phrase.text);
    const hide = h('input', { type: 'checkbox' });
    hide.checked = hideText;
    hide.addEventListener('change', () => { hideText = hide.checked; text.classList.toggle('blurred', hideText); });
    const mic = MicButton({
      onResult: async said => {
        try {
          const res = await api('/score', { expected: phrase.text, actual: said });
          Progress.record('speaking', phrase.id, res.score, 100);
          text.classList.remove('blurred');
          result.replaceChildren(ComparisonView(res));
        } catch (e) {
          toast(e.message, 'error');
        }
      },
    });
    area.replaceChildren(h('div', { class: 'card' },
      h('div', { class: 'muted small' }, `${data.topics[topic]} · фраза ${position + 1} из ${queue.length} · `, levelBadge(phrase.level)),
      text,
      h('div', { class: 'ru' }, phrase.ru),
      h('div', { class: 'actions' }, SpeakButtons(() => phrase.text)),
      h('label', { class: 'check' }, hide, ' Скрыть текст — повторять только на слух'),
      h('p', { class: 'muted small' }, 'Послушайте фразу, нажмите «Говорить» и повторите её вслух.'),
      mic,
      result,
      h('div', { class: 'actions' }, h('button', { class: 'btn secondary', type: 'button', onclick: () => { position++; show(); } }, 'Следующая фраза →')),
    ));
  }

  const wrap = h('div', {}, h('div', { class: 'toolbar' }, h('span', {}, 'Тема:'), select), area);
  start(topic);
  return wrap;
}

function QuestionPractice(questions) {
  let level = storageGet('et-question-level', 'all');
  let queue = [], position = 0;
  const area = h('div', {});

  function start(newLevel) {
    level = newLevel;
    storageSet('et-question-level', level);
    queue = shuffle(questions.filter(q => level === 'all' || q.level === level));
    position = 0;
    show();
  }

  function show() {
    if (position >= queue.length) { queue = shuffle(queue); position = 0; }
    const q = queue[position];
    const result = h('div', {});
    const mic = MicButton({
      continuous: true,
      onResult: async said => {
        try {
          const res = await api(`/speaking/questions/${q.id}/check`, { answer: said });
          Progress.record('answer', q.id, Math.min(res.words, res.min_words), res.min_words);
          result.replaceChildren(h('div', { class: `comparison ${res.enough ? 'good' : 'ok'}` },
            h('div', { class: 'verdict' }, res.feedback),
            h('div', {}, 'Вы сказали: ', h('i', {}, said || '—')),
            h('div', { class: 'muted small' }, `Слов: ${res.words} (рекомендуется от ${res.min_words})`),
            h('div', { class: 'sample' }, SpeakIcon(res.sample), h('div', {}, h('div', { class: 'muted small' }, 'Пример ответа:'), res.sample)),
          ));
        } catch (e) {
          toast(e.message, 'error');
        }
      },
    });
    area.replaceChildren(h('div', { class: 'card' },
      h('div', { class: 'muted small' }, `Вопрос ${position + 1} из ${queue.length} · `, levelBadge(q.level)),
      h('div', { class: 'phrase' }, q.question),
      h('div', { class: 'ru' }, q.ru),
      h('div', { class: 'actions' }, SpeakButtons(() => q.question)),
      h('p', { class: 'muted small' }, 'Нажмите «Говорить», ответьте развёрнуто, затем нажмите «Готово».'),
      mic,
      result,
      h('div', { class: 'actions' }, h('button', { class: 'btn secondary', type: 'button', onclick: () => { position++; show(); } }, 'Следующий вопрос →')),
    ));
    Voice.speak(q.question);
  }

  const wrap = h('div', {}, LevelChips(['all', 'A1', 'A2', 'B1', 'B2'], level, start), area);
  start(level);
  return wrap;
}

function FreeSpeech() {
  const log = h('div', { class: 'free-log' });
  const mic = MicButton({
    continuous: true,
    onResult: said => {
      const words = said ? said.split(/\s+/).length : 0;
      log.prepend(h('div', { class: 'bubble user' },
        said || '— ничего не распознано —',
        h('div', { class: 'muted small' }, `${words} ${plural(words, 'слово', 'слова', 'слов')}`),
        said ? SpeakIcon(said) : null,
      ));
      if (said) Progress.record('free', new Date().toISOString().slice(0, 10), 1, 1);
    },
  });
  return h('div', { class: 'card' },
    h('p', {}, 'Говорите на любую тему: расскажите о своём дне, планах, любимом фильме. Сайт покажет, как вас понял распознаватель речи — если текст совпадает с тем, что вы хотели сказать, значит вас поймёт и собеседник.'),
    h('p', { class: 'muted small' }, 'Идеи: «Describe your best friend», «What did you do yesterday?», «Tell me about your city».'),
    mic,
    log,
  );
}

// dialogues

async function pageDialogues() {
  const dialogues = await api('/dialogues');
  return h('div', {},
    h('h1', {}, '💬 Диалоги'),
    h('p', { class: 'muted' }, 'Ролевые диалоги: собеседник говорит, вы отвечаете голосом (или текстом). Ответ засчитывается, если он подходит по смыслу.'),
    h('div', { class: 'grid' }, dialogues.map(d => {
      const result = Progress.get('dialogue', d.id);
      return h('a', { class: 'card', href: `#/dialogues/${d.id}` },
        h('div', { class: 'card-top' }, levelBadge(d.level), result ? h('span', { class: 'best' }, `лучший: ${result.best}%`) : null),
        h('h3', {}, d.title),
        h('p', {}, d.description),
        h('div', { class: 'muted small' }, `${d.turns} ${plural(d.turns, 'реплика', 'реплики', 'реплик')}`),
      );
    })),
  );
}

async function pageDialogue(id) {
  const d = await api(`/dialogues/${id}`);
  const chat = h('div', { class: 'chat' });
  const controls = h('div', { class: 'chat-controls' });
  let turn = 0, firstTry = 0, attempts = 0, skipped = 0;
  let textMode = !Mic.supported(); // once the learner switches to typing, keep the field open

  const scroll = () => setTimeout(() => chat.scrollTo({ top: chat.scrollHeight, behavior: 'smooth' }), 50);

  function partnerSays(line, ru) {
    const ruBox = h('div', { class: `ru${Settings.get().showRu ? '' : ' hidden'}` }, ru);
    chat.append(h('div', { class: 'bubble partner' },
      h('div', { class: 'who' }, d.partner),
      h('div', {}, line, ' ', SpeakIcon(line)),
      ruBox,
      Settings.get().showRu ? null : h('button', { class: 'link', type: 'button', onclick: e => { ruBox.classList.remove('hidden'); e.target.remove(); } }, 'перевод'),
    ));
    scroll();
    if (Settings.get().autoplay) Voice.speak(line);
  }

  function system(text, cls = '') {
    chat.append(h('div', { class: `bubble system ${cls}` }, text));
    scroll();
  }

  async function reply(text) {
    if (!text) { system('Я ничего не услышал. Попробуйте ещё раз.', 'bad'); return; }
    chat.append(h('div', { class: 'bubble user' }, text));
    scroll();
    attempts++;
    let res;
    try {
      res = await api(`/dialogues/${id}/check`, { turn, answer: text });
    } catch (e) {
      toast(e.message, 'error');
      return;
    }
    if (res.accepted) {
      if (attempts === 1) firstTry++;
      advance();
    } else {
      system(res.feedback, 'bad');
    }
  }

  function advance() {
    turn++;
    attempts = 0;
    if (turn < d.turns.length) {
      const t = d.turns[turn];
      setTimeout(() => partnerSays(t.line, t.ru), 400);
      renderControls();
    } else {
      setTimeout(finish, 400);
    }
  }

  function finish() {
    partnerSays(d.final, d.final_ru);
    const total = d.turns.length;
    Progress.record('dialogue', id, firstTry, total);
    controls.replaceChildren(h('div', { class: 'result' },
      h('div', { class: 'result-emoji' }, firstTry === total ? '🏆' : '🎉'),
      h('h2', {}, 'Диалог завершён!'),
      h('p', {}, `С первой попытки: ${firstTry} из ${total}`, skipped ? ` · пропущено: ${skipped}` : ''),
      h('div', { class: 'actions center' },
        h('button', { class: 'btn primary', type: 'button', onclick: () => router() }, '🔁 Ещё раз'),
        h('a', { class: 'btn secondary', href: '#/dialogues' }, '← Все диалоги'),
      ),
    ));
  }

  function renderControls() {
    const t = d.turns[turn];
    const hintBox = h('div', { class: 'hint hidden' }, '💡 Например: ', h('b', {}, t.hint), ' ', SpeakIcon(t.hint));
    const textForm = h('form', {
      class: 'input-row hidden',
      onsubmit: e => {
        e.preventDefault();
        const input = textForm.querySelector('input');
        const value = input.value.trim();
        if (value) { input.value = ''; reply(value); }
      },
    }, h('input', { class: 'text-input', type: 'text', placeholder: 'Напишите ответ по-английски…' }), h('button', { class: 'btn primary', type: 'submit' }, 'Отправить'));
    controls.replaceChildren(
      h('div', { class: 'muted small' }, `Ваша реплика ${turn + 1} из ${d.turns.length}`),
      Mic.supported() ? MicButton({ onResult: reply, continuous: Boolean(t.min_words) }) : null,
      h('div', { class: 'actions' },
        h('button', { class: 'btn small ghost', type: 'button', onclick: () => hintBox.classList.toggle('hidden') }, '💡 Подсказка'),
        h('button', {
          class: 'btn small ghost', type: 'button',
          onclick: () => {
            textMode = textForm.classList.toggle('hidden') === false;
            if (textMode) textForm.querySelector('input').focus();
          },
        }, '⌨️ Ответить текстом'),
        h('button', {
          class: 'btn small ghost', type: 'button',
          onclick: () => { skipped++; system(`Пропущено. Можно было ответить: «${t.hint}»`); advance(); },
        }, '⏭ Пропустить'),
      ),
      hintBox,
      textForm,
    );
    if (textMode) {
      textForm.classList.remove('hidden');
      textForm.querySelector('input').focus();
    }
  }

  const view = h('div', { class: 'narrow' },
    h('a', { class: 'crumb', href: '#/dialogues' }, '← Все диалоги'),
    h('h1', {}, d.title, ' ', levelBadge(d.level)),
    h('p', { class: 'muted' }, d.description),
    h('div', { class: 'card chat-card' }, chat, controls),
  );
  partnerSays(d.turns[0].line, d.turns[0].ru);
  renderControls();
  return view;
}

// progress & settings

async function pageProgress() {
  const overview = overviewCache || (overviewCache = await api('/overview'));
  const data = Progress.load();
  const avg = list => (list.length ? Math.round(list.reduce((s, r) => s + r.best, 0) / list.length) + '%' : '—');
  const tests = Progress.byKind('test');
  const lessons = Progress.byKind('grammar');
  const dictation = Progress.byKind('dictation');
  const speaking = Progress.byKind('speaking');
  const dialogues = Progress.byKind('dialogue');

  const settings = Settings.get();
  const voiceSelect = h('select', { class: 'select' },
    h('option', { value: '' }, 'Автоматически'),
    Voice.voices.map(v => h('option', { value: v.voiceURI }, `${v.name} (${v.lang})`)),
  );
  voiceSelect.value = settings.voice;
  voiceSelect.addEventListener('change', () => Settings.set({ voice: voiceSelect.value }));

  const rate = h('input', { type: 'range', min: '0.6', max: '1.3', step: '0.05', value: String(settings.rate) });
  const rateLabel = h('span', {}, `${settings.rate}×`);
  rate.addEventListener('input', () => { rateLabel.textContent = `${rate.value}×`; Settings.set({ rate: Number(rate.value) }); });

  const radio = (name, value, label) => {
    const input = h('input', { type: 'radio', name, value });
    input.checked = settings[name] === value;
    input.addEventListener('change', () => { Settings.set({ [name]: value }); if (name === 'stt') Mic.forceServer = false; });
    return h('label', { class: 'check' }, input, ' ', label);
  };
  const checkbox = (name, label) => {
    const input = h('input', { type: 'checkbox' });
    input.checked = Boolean(settings[name]);
    input.addEventListener('change', () => Settings.set({ [name]: input.checked }));
    return h('label', { class: 'check' }, input, ' ', label);
  };

  return h('div', { class: 'narrow' },
    h('h1', {}, '📊 Прогресс'),
    h('section', { class: 'stats' },
      stat('🔥', Progress.streak(), plural(Progress.streak(), 'день подряд', 'дня подряд', 'дней подряд')),
      stat('📅', data.days.length, 'дней занятий'),
      stat('📝', `${tests.length}/${overview.tests}`, `тестов · средний ${avg(tests)}`),
      stat('📘', `${lessons.filter(l => l.best >= 70).length}/${overview.grammar}`, 'тем изучено'),
      stat('✍️', dictation.length, `диктантов · средний ${avg(dictation)}`),
      stat('🗣', speaking.length, `фраз · точность ${avg(speaking)}`),
      stat('💬', `${dialogues.length}/${overview.dialogues}`, 'диалогов пройдено'),
    ),
    h('section', { class: 'card' },
      h('h2', {}, '⚙️ Настройки'),
      h('div', { class: 'setting' }, h('div', { class: 'setting-name' }, 'Озвучка'),
        radio('tts', 'auto', 'Голос браузера (если есть английский голос)'),
        radio('tts', 'server', 'Голос сервера (Google)')),
      h('div', { class: 'setting' }, h('div', { class: 'setting-name' }, 'Голос браузера'), voiceSelect,
        Voice.voices.length ? null : h('div', { class: 'muted small' }, 'Английские голоса в браузере не найдены — используется голос сервера.')),
      h('div', { class: 'setting' }, h('div', { class: 'setting-name' }, 'Скорость речи'), rate, ' ', rateLabel,
        h('button', { class: 'btn small ghost', type: 'button', onclick: () => Voice.speak('Hello! This is how I sound. Let\'s practice English together.') }, '🔊 Проверить')),
      h('div', { class: 'setting' }, h('div', { class: 'setting-name' }, 'Распознавание речи'),
        radio('stt', 'auto', 'Автоматически (в браузере, если поддерживается)'),
        radio('stt', 'server', 'На сервере (запись звука отправляется на сервер)')),
      h('div', { class: 'setting' }, h('div', { class: 'setting-name' }, 'Диалоги'),
        checkbox('autoplay', 'Автоматически озвучивать реплики собеседника'),
        checkbox('showRu', 'Сразу показывать перевод реплик')),
    ),
    h('section', { class: 'card' },
      h('h2', {}, 'Сброс'),
      h('p', { class: 'muted' }, 'Прогресс хранится только в этом браузере.'),
      h('button', {
        class: 'btn danger', type: 'button',
        onclick: () => { if (confirm('Удалить весь прогресс?')) { Progress.reset(); router(); } },
      }, '🗑 Сбросить прогресс'),
    ),
  );
}

// ------------------------------------------------------------------- router

const routes = [
  [/^$/, pageHome],
  [/^tests$/, pageTests],
  [/^tests\/([\w-]+)$/, pageTest],
  [/^grammar$/, pageGrammar],
  [/^grammar\/([\w-]+)$/, pageLesson],
  [/^listening$/, pageListening],
  [/^listening\/([\w-]+)$/, pageListeningText],
  [/^speaking$/, pageSpeaking],
  [/^dialogues$/, pageDialogues],
  [/^dialogues\/([\w-]+)$/, pageDialogue],
  [/^progress$/, pageProgress],
];

let navigation = 0;

async function router() {
  const token = ++navigation;
  Voice.stop();
  Mic.abort();
  const path = location.hash.replace(/^#\/?/, '').replace(/\/$/, '');
  const app = document.getElementById('app');
  const section = path.split('/')[0];
  document.querySelectorAll('#nav a').forEach(a => a.classList.toggle('active', a.dataset.section === section));
  document.getElementById('nav').classList.remove('open');

  const route = routes.find(([re]) => re.test(path));
  if (!route) {
    app.replaceChildren(h('div', { class: 'narrow' }, h('h1', {}, 'Страница не найдена'), h('a', { href: '#/' }, '← На главную')));
    return;
  }
  app.replaceChildren(h('div', { class: 'loading' }, 'Загрузка…'));
  try {
    const view = await route[1](...path.match(route[0]).slice(1));
    if (token !== navigation) return;
    app.replaceChildren(view);
    window.scrollTo(0, 0);
  } catch (e) {
    if (token !== navigation) return;
    app.replaceChildren(h('div', { class: 'narrow' }, h('h1', {}, 'Что-то пошло не так'), h('p', {}, e.message), h('a', { href: '#/' }, '← На главную')));
  }
}

document.getElementById('menu-toggle').addEventListener('click', () => {
  const nav = document.getElementById('nav');
  nav.classList.toggle('open');
  document.getElementById('menu-toggle').setAttribute('aria-expanded', nav.classList.contains('open'));
});

Voice.init();
window.addEventListener('hashchange', router);
router();
