// Pyodide runner — запуск Python через WebAssembly
// Для JS/C++ будет заглушка (расширяется позже)

const PyodideRunner = (() => {
  let pyodide = null;
  let loading = false;
  let ready = false;

  async function load() {
    if (ready) return pyodide;
    if (loading) {
      // ждём загрузки
      return new Promise((resolve) => {
        const interval = setInterval(() => {
          if (ready) { clearInterval(interval); resolve(pyodide); }
        }, 100);
      });
    }
    loading = true;
    // Загружаем Pyodide из CDN
    const script = document.createElement('script');
    script.src = 'https://cdn.jsdelivr.net/pyodide/v0.24.1/full/pyodide.js';
    document.head.appendChild(script);
    await new Promise((res, rej) => { script.onload = res; script.onerror = rej; });
    pyodide = await loadPyodide({ indexURL: 'https://cdn.jsdelivr.net/pyodide/v0.24.1/full/' });
    ready = true;
    return pyodide;
  }

  async function runPython(code, onOutput) {
    const py = await load();

    // Перехватываем stdout
    let output = '';
    py.globals.set('_print_output', (text) => {
      output += text + '\n';
      if (onOutput) onOutput(text);
    });

    // Заменяем print
    const wrappedCode = `
import sys
class _CaptureOut:
    def write(self, text):
        if text.strip():
            _print_output(text)
    def flush(self): pass
sys.stdout = _CaptureOut()
sys.stderr = _CaptureOut()
${code}
`;
    try {
      await py.runPythonAsync(wrappedCode);
      return { success: true, output };
    } catch (err) {
      return { success: false, output: err.message };
    }
  }

  return { runPython, load };
})();

// Простая заглушка для JS
async function runJavaScript(code) {
  try {
    const logs = [];
    const fakeConsole = { log: (...a) => logs.push(a.join(' ')) };
    const fn = new Function('console', code);
    fn(fakeConsole);
    return { success: true, output: logs.join('\n') || '(нет вывода)' };
  } catch (err) {
    return { success: false, output: err.message };
  }
}

window.codeRunner = {
  async run(code, lang) {
    if (lang === 'python') return PyodideRunner.runPython(code);
    if (lang === 'javascript') return runJavaScript(code);
    return { success: false, output: `Запуск ${lang} пока не поддерживается` };
  }
};
