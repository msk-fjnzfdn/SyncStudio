/* ── Room page logic ── */
(async function () {
  const layout = document.querySelector('.room-layout');
  if (!layout) return;

  const ROLE    = layout.dataset.role;
  const ROOM_ID = layout.dataset.room;
  const USER_ID = layout.dataset.user;

  // ── Monaco setup ──────────────────────────────────────────
  require.config({ paths: { vs: 'https://cdn.jsdelivr.net/npm/monaco-editor@0.45.0/min/vs' } });

  const monacoTheme = {
    base: 'vs-dark', inherit: true,
    rules: [
      { token: 'comment', foreground: '555550' },
      { token: 'keyword', foreground: '39d353', fontStyle: 'normal' },
      { token: 'string',  foreground: 'e8b339' },
      { token: 'number',  foreground: '5590e8' },
    ],
    colors: {
      'editor.background':           '#0a0a0a',
      'editor.foreground':           '#e8e6e0',
      'editor.lineHighlightBackground': '#111111',
      'editorLineNumber.foreground': '#333330',
      'editorCursor.foreground':     '#39d353',
      'editor.selectionBackground':  '#1a5c2640',
      'editorIndentGuide.background1': '#1e1e1e',
    }
  };

  const editors = {};
  let currentLang = 'python';
  let isTeacherEditing = false;

  function langToMonaco(lang) {
    return lang === 'cpp' ? 'cpp' : lang;
  }
  function langToExt(lang) {
    return { python: 'py', javascript: 'js', cpp: 'cpp' }[lang] || 'txt';
  }

  function createEditor(containerId, readOnly = false) {
    return new Promise((resolve) => {
      require(['vs/editor/editor.main'], () => {
        monaco.editor.defineTheme('syncstudio', monacoTheme);
        const el = document.getElementById(containerId);
        if (!el) { resolve(null); return; }
        const ed = monaco.editor.create(el, {
          value: '',
          language: 'python',
          theme: 'syncstudio',
          readOnly,
          fontSize: 13,
          fontFamily: '"JetBrains Mono", monospace',
          fontLigatures: true,
          lineHeight: 22,
          minimap: { enabled: false },
          scrollBeyondLastLine: false,
          renderLineHighlight: 'line',
          padding: { top: 12, bottom: 12 },
          smoothScrolling: true,
        });
        new ResizeObserver(() => ed.layout()).observe(el);
        resolve(ed);
      });
    });
  }

  // init editors
  editors.own = await createEditor('ownEditor', false);

  if (ROLE === 'teacher') {
    editors.student = await createEditor('studentEditor', false);
  } else {
    editors.teacher = await createEditor('teacherEditor', true);
  }

  // ── Language switching ─────────────────────────────────────
  document.querySelectorAll('.lang-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.lang-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      currentLang = btn.dataset.lang;

      const monacoLang = langToMonaco(currentLang);
      if (editors.own) monaco.editor.setModelLanguage(editors.own.getModel(), monacoLang);

      const fname = document.getElementById('ownFileName');
      if (fname) fname.textContent = `main.${langToExt(currentLang)}`;
    });
  });

  // ── Tab switching ──────────────────────────────────────────
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const tab = btn.dataset.tab;
      document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
      document.querySelectorAll('.editor-pane').forEach(p => p.classList.remove('active'));
      btn.classList.add('active');

      const pane = document.getElementById(tab === 'own' ? 'paneOwn' :
                   tab === 'student' ? 'paneStudent' : 'paneTeacher');
      if (pane) {
        pane.classList.add('active');
        setTimeout(() => {
          if (tab === 'own' && editors.own) editors.own.layout();
          if (tab === 'student' && editors.student) editors.student.layout();
          if (tab === 'teacher' && editors.teacher) editors.teacher.layout();
        }, 10);
      }
    });
  });

  // ── WebSocket ──────────────────────────────────────────────
  const wsUrl = ROLE === 'teacher'
    ? `ws://${WS_HOST}/ws/${ROOM_ID}/teacher`
    : `ws://${WS_HOST}/ws/${ROOM_ID}/student/${USER_ID}`;

  let ws = null;
  let debounceTimer = null;
  let editStudentDebounce = null;
  let viewingStudentId = null;

  function setWsStatus(connected) {
    const el = document.getElementById('wsStatus');
    if (!el) return;
    const dot = el.querySelector('.dot');
    const label = el.querySelector('span:last-child');
    if (connected) {
      dot.className = 'dot connected';
      label.textContent = 'подключено';
    } else {
      dot.className = 'dot disconnected';
      label.textContent = 'отключено';
    }
  }

  function connectWS() {
    ws = new WebSocket(wsUrl);

    ws.onopen = () => {
      setWsStatus(true);
    };

    ws.onclose = () => {
      setWsStatus(false);
      setTimeout(connectWS, 3000); // переподключение
    };

    ws.onerror = () => ws.close();

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        handleMessage(msg);
      } catch {}
    };
  }

  function sendJson(data) {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify(data));
    }
  }

  function handleMessage(msg) {
    switch (msg.type) {

      case 'teacher_code_broadcast':
        if (ROLE === 'student' && editors.teacher) {
          editors.teacher.setValue(msg.code || '');
          if (msg.lang) {
            monaco.editor.setModelLanguage(editors.teacher.getModel(), langToMonaco(msg.lang));
          }
        }
        break;

      case 'student_code_snapshot':
        if (ROLE === 'teacher') {
          if (editors.student) {
            editors.student.setValue(msg.code || '');
            if (msg.lang) monaco.editor.setModelLanguage(editors.student.getModel(), langToMonaco(msg.lang));
          }
          viewingStudentId = msg.student_id;
          const tab = document.getElementById('studentTab');
          const nameEl = document.getElementById('studentTabName');
          const fname  = document.getElementById('studentFileName');
          if (tab) tab.style.display = 'inline-block';
          if (nameEl) nameEl.textContent = msg.student_id;
          if (fname) fname.textContent = `student_${msg.student_id}.${langToExt(msg.lang || 'python')}`;

          const viewInfo = document.getElementById('viewingInfo');
          const stopBtn  = document.getElementById('stopViewBtn');
          if (viewInfo) viewInfo.innerHTML = `<span class="viewing-active">↗ ${msg.student_id}</span>`;
          if (stopBtn)  stopBtn.style.display = 'block';

          // переключаем на вкладку ученика
          document.querySelectorAll('.tab-btn').forEach(b => {
            b.classList.toggle('active', b.dataset.tab === 'student');
          });
          document.querySelectorAll('.editor-pane').forEach(p => p.classList.remove('active'));
          document.getElementById('paneStudent')?.classList.add('active');
          setTimeout(() => editors.student?.layout(), 10);
        }
        break;

      case 'teacher_edit':
        if (ROLE === 'student' && editors.own) {
          isTeacherEditing = true;
          editors.own.setValue(msg.code || '');
          showEditBanner();
          clearTimeout(window._editFlagTimer);
          window._editFlagTimer = setTimeout(() => { isTeacherEditing = false; }, 2000);
        }
        break;

      case 'student_joined':
        if (ROLE === 'teacher') addStudentToList(msg.student_id);
        break;

      case 'student_left':
        if (ROLE === 'teacher') removeStudentFromList(msg.student_id);
        break;
    }
  }

  // ── Own code → send to server ──────────────────────────────
  if (editors.own) {
    editors.own.onDidChangeModelContent(() => {
      if (isTeacherEditing) return;
      clearTimeout(debounceTimer);
      debounceTimer = setTimeout(() => {
        sendJson({
          type: 'code_update',
          code: editors.own.getValue(),
          lang: currentLang,
        });
      }, 180);
    });
  }

  // ── Teacher editing student code ───────────────────────────
  if (ROLE === 'teacher' && editors.student) {
    editors.student.onDidChangeModelContent(() => {
      if (!viewingStudentId) return;
      clearTimeout(editStudentDebounce);
      editStudentDebounce = setTimeout(() => {
        sendJson({
          type: 'edit_student',
          student_id: viewingStudentId,
          code: editors.student.getValue(),
          lang: currentLang,
        });
      }, 200);
    });
  }

  // ── Stop viewing student ───────────────────────────────────
  document.getElementById('stopViewBtn')?.addEventListener('click', () => {
    sendJson({ type: 'stop_viewing' });
    viewingStudentId = null;
    const viewInfo = document.getElementById('viewingInfo');
    const stopBtn  = document.getElementById('stopViewBtn');
    if (viewInfo) viewInfo.innerHTML = '<span class="viewing-none">никто не выбран</span>';
    if (stopBtn)  stopBtn.style.display = 'none';
    // вернуться к своему коду
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.toggle('active', b.dataset.tab === 'own'));
    document.querySelectorAll('.editor-pane').forEach(p => p.classList.remove('active'));
    document.getElementById('paneOwn')?.classList.add('active');
    setTimeout(() => editors.own?.layout(), 10);
  });

  // ── Run code ───────────────────────────────────────────────
  async function runCode(code, lang, outputEl) {
    if (!outputEl) return;
    outputEl.className = 'output-content running';
    outputEl.textContent = '⟳ выполняется...';

    const result = await window.codeRunner.run(code, lang);
    outputEl.className = result.success ? 'output-content success' : 'output-content error';
    outputEl.textContent = result.output || (result.success ? '(нет вывода)' : '(ошибка без сообщения)');
  }

  document.getElementById('runOwnBtn')?.addEventListener('click', () => {
    if (!editors.own) return;
    const out = document.getElementById('ownOutputContent');
    runCode(editors.own.getValue(), currentLang, out);
  });

  // ── Students list (teacher) ────────────────────────────────
  function addStudentToList(studentId) {
    const list = document.getElementById('studentsList');
    if (!list) return;
    const noEl = list.querySelector('.no-students');
    if (noEl) noEl.remove();

    if (list.querySelector(`[data-id="${studentId}"]`)) return;

    const item = document.createElement('div');
    item.className = 'student-item';
    item.dataset.id = studentId;
    item.innerHTML = `
      <span class="student-name">${studentId}</span>
      <span class="student-dot"></span>
    `;
    item.addEventListener('click', () => {
      sendJson({ type: 'view_student', student_id: studentId });
      list.querySelectorAll('.student-item').forEach(i => i.classList.remove('viewing'));
      item.classList.add('viewing');
    });
    list.appendChild(item);
  }

  function removeStudentFromList(studentId) {
    const list = document.getElementById('studentsList');
    if (!list) return;
    list.querySelector(`[data-id="${studentId}"]`)?.remove();
    if (!list.children.length) {
      list.innerHTML = '<div class="no-students">нет подключённых учеников</div>';
    }
    if (viewingStudentId === studentId) {
      document.getElementById('stopViewBtn')?.click();
    }
  }

  // ── Teacher-edit banner (student) ─────────────────────────
  function showEditBanner() {
    const pane = document.getElementById('paneOwn');
    if (!pane) return;
    let banner = pane.querySelector('.edit-banner');
    if (!banner) {
      banner = document.createElement('div');
      banner.className = 'edit-banner';
      banner.textContent = '✎ учитель редактирует ваш код';
      pane.querySelector('.editor-topbar').after(banner);
    }
    clearTimeout(banner._timer);
    banner.style.display = 'block';
    banner._timer = setTimeout(() => { banner.style.display = 'none'; }, 3000);
  }

  // ── Toast ──────────────────────────────────────────────────
  window.showToast = function (text, type = '') {
    const t = document.getElementById('toast');
    if (!t) return;
    t.textContent = text;
    t.className = `toast show ${type}`;
    clearTimeout(t._timer);
    t._timer = setTimeout(() => { t.className = 'toast'; }, 3000);
  };

  // ── Start ──────────────────────────────────────────────────
  connectWS();
})();
