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
      'editor.background':              '#0a0a0a',
      'editor.foreground':              '#e8e6e0',
      'editor.lineHighlightBackground': '#111111',
      'editorLineNumber.foreground':    '#333330',
      'editorCursor.foreground':        '#39d353',
      'editor.selectionBackground':     '#1a5c2640',
      'editorIndentGuide.background1':  '#1e1e1e',
    }
  };

  const editors = {};
  let currentLang      = 'python';
  let isTeacherEditing = false;

  function langToMonaco(lang) {
    return lang === 'cpp' ? 'cpp' : lang;
  }
  function langToExt(lang) {
    return { python: 'py', javascript: 'js', cpp: 'cpp' }[lang] || 'txt';
  }
  function langToMime(lang) {
    return { python: 'text/x-python', javascript: 'text/javascript', cpp: 'text/x-c++src' }[lang] || 'text/plain';
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
      if (editors.own) {
        monaco.editor.setModelLanguage(editors.own.getModel(), monacoLang);
        sendJson({
          type: 'code_update',
          code: editors.own.getValue(),
          lang: currentLang,
        });
      }

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
          if (tab === 'own'     && editors.own)     editors.own.layout();
          if (tab === 'student' && editors.student)  editors.student.layout();
          if (tab === 'teacher' && editors.teacher)  editors.teacher.layout();
        }, 10);
      }
    });
  });

  // ── WebSocket ──────────────────────────────────────────────
  const wsProtocol = window.location.protocol === 'https:' ? 'wss' : 'ws';
  const wsUrl = ROLE === 'teacher'
    ? `${wsProtocol}://${WS_HOST}/ws/${ROOM_ID}/teacher`
    : `${wsProtocol}://${WS_HOST}/ws/${ROOM_ID}/student/${USER_ID}`;

  let ws                  = null;
  let debounceTimer       = null;
  let editStudentDebounce = null;
  let viewingStudentId    = null;
  let viewingStudentLang  = 'python';

  function setWsStatus(connected) {
    const el = document.getElementById('wsStatus');
    if (!el) return;
    const dot   = el.querySelector('.dot');
    const label = el.querySelector('span:last-child');
    if (connected) {
      dot.className   = 'dot connected';
      label.textContent = 'подключено';
    } else {
      dot.className   = 'dot disconnected';
      label.textContent = 'отключено';
      if (ROLE === 'teacher') {
        const list = document.getElementById('studentsList');
        if (list) list.innerHTML = '<div class="no-students">переподключение...</div>';
      }
    }
  }

  function connectWS() {
    ws = new WebSocket(wsUrl);
    ws.onopen  = () => setWsStatus(true);
    ws.onclose = () => { setWsStatus(false); setTimeout(connectWS, 3000); };
    ws.onerror = () => ws.close();
    ws.onmessage = (event) => {
      try { handleMessage(JSON.parse(event.data)); }
      catch (err) { console.error('WS Message Error:', err); }
    };
  }

  function sendJson(data) {
    if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(data));
  }

  // ── Message handler ────────────────────────────────────────
  function handleMessage(msg) {
    switch (msg.type) {

      // ── Ученик получает код учителя ──
      case 'teacher_code_broadcast':
        if (ROLE === 'student' && editors.teacher) {
          editors.teacher.setValue(msg.code || '');
          if (msg.lang) monaco.editor.setModelLanguage(editors.teacher.getModel(), langToMonaco(msg.lang));
        }
        break;

      // ── Учитель получает снимок кода ученика ──
      case 'student_code_snapshot':
        if (ROLE === 'teacher') {
          if (editors.student) {
            if (editors.student.getValue() !== msg.code)
              editors.student.setValue(msg.code || '');
            if (msg.lang) monaco.editor.setModelLanguage(editors.student.getModel(), langToMonaco(msg.lang));
          }
          viewingStudentId   = msg.student_id;
          viewingStudentLang = msg.lang || 'python';

          const tab     = document.getElementById('studentTab');
          const nameEl  = document.getElementById('studentTabName');
          const fname   = document.getElementById('studentFileName');
          const viewInfo = document.getElementById('viewingInfo');
          const stopBtn  = document.getElementById('stopViewBtn');

          if (tab)      tab.style.display = 'inline-block';
          if (nameEl)   nameEl.textContent = msg.student_id;
          if (fname)    fname.textContent  = `student_${msg.student_id}.${langToExt(msg.lang || 'python')}`;
          if (viewInfo) viewInfo.innerHTML = `<span class="viewing-active">↗ ${msg.student_id}</span>`;
          if (stopBtn)  stopBtn.style.display = 'block';

          if (!msg.live) {
            document.querySelectorAll('.tab-btn').forEach(b =>
              b.classList.toggle('active', b.dataset.tab === 'student'));
            document.querySelectorAll('.editor-pane').forEach(p => p.classList.remove('active'));
            document.getElementById('paneStudent')?.classList.add('active');
            setTimeout(() => editors.student?.layout(), 10);
          }
        }
        break;

      // ── Учитель начал наблюдать — блокируем ученика ──
      case 'teacher_watching':
        if (ROLE === 'student' && editors.own) {
          editors.own.updateOptions({ readOnly: true });
          showWatchBanner(true);
        }
        break;

      // ── Учитель перестал наблюдать — разблокируем ученика ──
      case 'teacher_stopped_watching':
        if (ROLE === 'student' && editors.own) {
          editors.own.updateOptions({ readOnly: false });
          showWatchBanner(false);
        }
        break;

      // ── Учитель получает вывод консоли ученика ──
      case 'student_console_output':
        if (ROLE === 'teacher') {
          const studentOut = document.getElementById('studentOutputContent');
          if (studentOut) {
            studentOut.className  = msg.success ? 'output-content success' : 'output-content error';
            studentOut.textContent = msg.output || (msg.success ? '(нет вывода)' : '(ошибка без сообщения)');
          }
        }
        break;

      // ── Учитель редактирует код ученика ──
      case 'teacher_edit':
        if (ROLE === 'student' && editors.own) {
          isTeacherEditing = true;
          const state = editors.own.saveViewState();
          editors.own.setValue(msg.code || '');
          editors.own.restoreViewState(state);
          showEditBanner();
          clearTimeout(window._editFlagTimer);
          window._editFlagTimer = setTimeout(() => { isTeacherEditing = false; }, 2000);
        }
        break;

      // ── Список студентов ──
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
        sendJson({ type: 'code_update', code: editors.own.getValue(), lang: currentLang });
      }, 180);
    });
  }

  // ── Teacher editing student code → send live to server ─────
  if (ROLE === 'teacher' && editors.student) {
    editors.student.onDidChangeModelContent(() => {
      if (!viewingStudentId) return;
      clearTimeout(editStudentDebounce);
      editStudentDebounce = setTimeout(() => {
        sendJson({
          type: 'edit_student',
          student_id: viewingStudentId,
          code: editors.student.getValue(),
          lang: viewingStudentLang,
        });
      }, 200);
    });
  }

  // ── Stop viewing student ───────────────────────────────────
  function stopViewingStudent() {
    sendJson({ type: 'stop_viewing' });
    viewingStudentId   = null;
    viewingStudentLang = 'python';

    const viewInfo = document.getElementById('viewingInfo');
    const stopBtn  = document.getElementById('stopViewBtn');
    if (viewInfo) viewInfo.innerHTML = '<span class="viewing-none">никто не выбран</span>';
    if (stopBtn)  stopBtn.style.display = 'none';

    document.querySelectorAll('.student-item').forEach(i => i.classList.remove('viewing'));

    // Скрываем вкладку ученика и возвращаемся к своему редактору
    const studentTab = document.getElementById('studentTab');
    if (studentTab) studentTab.style.display = 'none';

    document.querySelectorAll('.tab-btn').forEach(b =>
      b.classList.toggle('active', b.dataset.tab === 'own'));
    document.querySelectorAll('.editor-pane').forEach(p => p.classList.remove('active'));
    document.getElementById('paneOwn')?.classList.add('active');

    // Очищаем редактор и вывод студента
    if (editors.student) editors.student.setValue('');
    const studentOut = document.getElementById('studentOutputContent');
    if (studentOut) { studentOut.className = 'output-content'; studentOut.textContent = 'ожидание запуска...'; }

    setTimeout(() => editors.own?.layout(), 10);
  }

  document.getElementById('stopViewBtn')?.addEventListener('click', stopViewingStudent);

  // ── Run code ───────────────────────────────────────────────
  async function runCode(code, lang, outputEl, sendConsole = false) {
    if (!outputEl) return;
    outputEl.className  = 'output-content running';
    outputEl.textContent = '⟳ выполняется...';

    const result = await window.codeRunner.run(code, lang);
    outputEl.className  = result.success ? 'output-content success' : 'output-content error';
    outputEl.textContent = result.output || (result.success ? '(нет вывода)' : '(ошибка без сообщения)');

    // Ученик отправляет вывод учителю (если тот наблюдает)
    if (sendConsole) {
      sendJson({
        type: 'console_output',
        output: result.output || (result.success ? '(нет вывода)' : '(ошибка без сообщения)'),
        success: result.success,
      });
    }
  }

  // Запуск своего кода (учитель и ученик)
  document.getElementById('runOwnBtn')?.addEventListener('click', () => {
    if (!editors.own) return;
    const out = document.getElementById('ownOutputContent');
    // Ученик передаёт консоль серверу; учитель — нет
    runCode(editors.own.getValue(), currentLang, out, ROLE === 'student');
  });

  // Учитель запускает код ученика локально
  document.getElementById('runStudentBtn')?.addEventListener('click', () => {
    if (!editors.student) return;
    const out = document.getElementById('studentOutputContent');
    runCode(editors.student.getValue(), viewingStudentLang, out, false);
  });

  // ── Save file (PATCH /add_file) ────────────────────────────
  async function saveCodeAsFile(code, lang, roomId, userId) {
    const ext      = langToExt(lang);
    const mime     = langToMime(lang);
    const filename = `main.${ext}`;
    const blob     = new Blob([code], { type: mime });
    const file     = new File([blob], filename, { type: mime });

    const formData = new FormData();
    formData.append('image', file, filename);

    try {
      const res = await fetch(`/add_file?room_id=${roomId}&user_id=${userId}`, {
        method: 'PATCH',
        body: formData,
      });
      const json = await res.json();
      if (json.error) {
        window.showToast(`Ошибка: ${json.error}`, 'error');
      } else {
        window.showToast('Файл сохранён ✓', 'success');
      }
    } catch (err) {
      window.showToast('Не удалось сохранить файл', 'error');
      console.error('Save error:', err);
    }
  }

  // Кнопка сохранения для ученика (свой код)
  document.getElementById('saveOwnBtn')?.addEventListener('click', () => {
    if (!editors.own) return;
    saveCodeAsFile(editors.own.getValue(), currentLang, ROOM_ID, USER_ID);
  });

  // Кнопка сохранения для учителя (код наблюдаемого ученика)
  document.getElementById('saveStudentBtn')?.addEventListener('click', () => {
    if (!editors.student || !viewingStudentId) return;
    saveCodeAsFile(editors.student.getValue(), viewingStudentLang, ROOM_ID, viewingStudentId);
  });

  // ── Students list (teacher) ────────────────────────────────
  function addStudentToList(studentId) {
    const list = document.getElementById('studentsList');
    if (!list) return;
    const noEl = list.querySelector('.no-students');
    if (noEl) noEl.remove();
    if (list.querySelector(`[data-id="${studentId}"]`)) return;

    const item = document.createElement('div');
    item.className  = 'student-item';
    item.dataset.id = studentId;
    item.innerHTML  = `
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
    if (list.children.length === 0)
      list.innerHTML = '<div class="no-students">нет подключённых учеников</div>';
    if (viewingStudentId === studentId) {
      window.showToast(`Ученик ${studentId} отключился`, 'error');
      stopViewingStudent();
    }
  }

  // ── Teacher watch banner (student) ────────────────────────
  function showWatchBanner(watching) {
    const pane = document.getElementById('paneOwn');
    if (!pane) return;
    let banner = pane.querySelector('.watch-banner');
    if (!banner) {
      banner = document.createElement('div');
      banner.className = 'watch-banner';
      pane.querySelector('.editor-topbar').after(banner);
    }
    banner.textContent = '👁 учитель наблюдает — редактирование заблокировано';
    banner.style.display = watching ? 'block' : 'none';
  }

  // ── Teacher edit banner (student) ─────────────────────────
  function showEditBanner() {
    const pane = document.getElementById('paneOwn');
    if (!pane) return;
    let banner = pane.querySelector('.edit-banner');
    if (!banner) {
      banner = document.createElement('div');
      banner.className  = 'edit-banner';
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
    t.className   = `toast show ${type}`;
    clearTimeout(t._timer);
    t._timer = setTimeout(() => { t.className = 'toast'; }, 3000);
  };

  // ── Start ──────────────────────────────────────────────────
  connectWS();
})();
