# -*- coding: utf-8 -*-
"""
PyIDE – VSCode Style con:
- Explorador de archivos
- Pestañas de edición (cerrables)
- Resaltado de sintaxis Python (keywords azul, strings rojo, comentarios gris)
- Abrir (simple/múltiple), Guardar, Guardar como
- Encriptar / Desencriptar (XOR)
- Deshacer / Rehacer / Seleccionar todo
- Ir a línea
- Depuración de sintaxis: marca errores de compilación y los muestra en Output
- Ejecutar código Python y mostrar stdout/stderr en Output
- Hotkeys: Ctrl+S, Ctrl+Shift+S, F5, Alt+V, Ctrl+Z, Ctrl+Shift+Z, Ctrl+A, Alt+G
"""

import sys
import os
import tempfile

from PySide6.QtCore import QDir, QRegularExpression, Qt, QProcess
from PySide6.QtGui import (
    QAction, QColor, QFont,
    QSyntaxHighlighter, QTextCharFormat, QTextCursor
)
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout,
    QTreeView, QFileSystemModel, QTabWidget,
    QPlainTextEdit, QStatusBar, QFileDialog, QMenuBar,
    QDockWidget, QInputDialog
)

# -------------------------------------------------
# XOR Cipher
# -------------------------------------------------
ENCRYPTION_KEY = 67

def xor_cipher(text, key=ENCRYPTION_KEY):
    return ''.join(chr(ord(c) ^ key) for c in text)

# -------------------------------------------------
# Syntax Highlighter mejorado
# -------------------------------------------------
class PythonHighlighter(QSyntaxHighlighter):
    def __init__(self, doc):
        super().__init__(doc)
        self.keyword_rules = []
        kw_fmt = QTextCharFormat()
        kw_fmt.setForeground(QColor("#569CD6"))
        kw_fmt.setFontWeight(QFont.Bold)
        keywords = [
            "import","from","class","def","if","elif","else","for","while",
            "return","in","and","or","not","with","as","try","except","finally",
            "pass","break","continue","yield","assert","async","await",
            "global","nonlocal","del","raise","is","lambda"
        ]
        for w in keywords:
            pat = QRegularExpression(rf"\b{w}\b")
            self.keyword_rules.append((pat, kw_fmt))

        self.comment_pattern = QRegularExpression(r"#.*")
        self.comment_format = QTextCharFormat()
        self.comment_format.setForeground(QColor("#888888"))

        self.string_pattern = QRegularExpression(r"(['\"]).*?\1")
        self.string_format = QTextCharFormat()
        self.string_format.setForeground(QColor("#A31515"))

    def highlightBlock(self, text):
        string_spans = []
        it = self.string_pattern.globalMatch(text)
        while it.hasNext():
            m = it.next()
            s, l = m.capturedStart(), m.capturedLength()
            self.setFormat(s, l, self.string_format)
            string_spans.append((s, l))

        comment_spans = []
        it = self.comment_pattern.globalMatch(text)
        while it.hasNext():
            m = it.next()
            s, l = m.capturedStart(), m.capturedLength()
            self.setFormat(s, l, self.comment_format)
            comment_spans.append((s, l))

        for pat, fmt in self.keyword_rules:
            it2 = pat.globalMatch(text)
            while it2.hasNext():
                m2 = it2.next()
                s, l = m2.capturedStart(), m2.capturedLength()
                if not self._inside_spans(s, string_spans) and not self._inside_spans(s, comment_spans):
                    self.setFormat(s, l, fmt)

    def _inside_spans(self, pos, spans):
        for start, length in spans:
            if start <= pos < start + length:
                return True
        return False

# -------------------------------------------------
# Main Window
# -------------------------------------------------
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PyIDE – VSCode Style")
        self.resize(1024, 768)

        # Árbol de archivos
        model = QFileSystemModel()
        model.setRootPath(QDir.currentPath())
        self.tree = QTreeView()
        self.tree.setModel(model)
        self.tree.setRootIndex(model.index(QDir.currentPath()))
        self.tree.doubleClicked.connect(self.open_from_tree)

        # Pestañas de editor
        self.tabs = QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.tabCloseRequested.connect(self.close_tab)

        # Layout central
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.addWidget(self.tree, 1)
        layout.addWidget(self.tabs, 3)
        self.setCentralWidget(container)

        # Status bar
        self.status = QStatusBar()
        self.setStatusBar(self.status)

        # Panel Output (stdout + stderr)
        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        dock = QDockWidget("Output", self)
        dock.setWidget(self.output)
        self.addDockWidget(Qt.BottomDockWidgetArea, dock)

        # QProcess para ejecutar Python (canales unidos)
        self.proc = QProcess(self)
        self.proc.setProcessChannelMode(QProcess.MergedChannels)
        self.proc.readyReadStandardOutput.connect(self.handle_stdout)
        self.proc.finished.connect(self.process_finished)

        # Menús y acciones con hotkeys
        menubar = QMenuBar()

        file_menu = menubar.addMenu("&File")
        file_menu.addAction(self._make_action("Open...", self.open_file))
        file_menu.addAction(self._make_action("Open Multiple...", self.open_multiple))
        file_menu.addSeparator()
        file_menu.addAction(self._make_action("Save", self.save_current, "Ctrl+S"))
        file_menu.addAction(self._make_action("Save As...", self.save_as_current, "Ctrl+Shift+S"))
        file_menu.addSeparator()
        file_menu.addAction(self._make_action("Exit", self.close))

        edit_menu = menubar.addMenu("&Edit")
        edit_menu.addAction(self._make_action("Undo", self.undo_current, "Ctrl+Z"))
        edit_menu.addAction(self._make_action("Redo", self.redo_current, "Ctrl+Shift+Z"))
        edit_menu.addAction(self._make_action("Select All", self.select_all_current, "Ctrl+A"))
        edit_menu.addSeparator()
        edit_menu.addAction(self._make_action("Encrypt", self.encrypt_current))
        edit_menu.addAction(self._make_action("Decrypt", self.decrypt_current))
        edit_menu.addSeparator()
        edit_menu.addAction(self._make_action("Go to Line...", self.go_to_line, "Alt+G"))

        run_menu = menubar.addMenu("&Run")
        run_menu.addAction(self._make_action("Debug (Syntax)", self.debug_current, "Alt+V"))
        run_menu.addAction(self._make_action("Run Code", self.run_current, "F5"))

        self.setMenuBar(menubar)

    def _make_action(self, text, handler, shortcut=None):
        act = QAction(text, self)
        act.triggered.connect(handler)
        if shortcut:
            act.setShortcut(shortcut)
        return act

    # --- Abrir / Guardar ---
    def open_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open File", "", "Python Files (*.py);;All Files (*)")
        if path:
            self._load_path(path)

    def open_multiple(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "Open Multiple", "", "Python Files (*.py);;All Files (*)")
        for p in paths:
            self._load_path(p)

    def open_from_tree(self, idx):
        p = self.tree.model().filePath(idx)
        if os.path.isfile(p):
            self._load_path(p)

    def _load_path(self, path):
        with open(path, 'r', encoding='utf-8') as f:
            text = f.read()
        editor = QPlainTextEdit()
        editor.setPlainText(text)
        editor.file_path = path
        PythonHighlighter(editor.document())
        title = os.path.basename(path)
        self.tabs.addTab(editor, title)
        self.status.showMessage(f"Opened: {path}", 5000)

    def save_current(self):
        ed = self.tabs.currentWidget()
        if not hasattr(ed, 'file_path') or not ed.file_path:
            return self.save_as_current()
        with open(ed.file_path, 'w', encoding='utf-8') as f:
            f.write(ed.toPlainText())
        self.status.showMessage(f"Saved: {ed.file_path}", 5000)

    def save_as_current(self):
        ed = self.tabs.currentWidget()
        path, _ = QFileDialog.getSaveFileName(self, "Save As", "", "Python Files (*.py);;All Files (*)")
        if not path:
            return
        with open(path, 'w', encoding='utf-8') as f:
            f.write(ed.toPlainText())
        ed.file_path = path
        self.tabs.setTabText(self.tabs.currentIndex(), os.path.basename(path))
        self.status.showMessage(f"Saved As: {path}", 5000)

    # --- Undo / Redo / Select All ---
    def undo_current(self):
        ed = self.tabs.currentWidget()
        if ed:
            ed.undo()

    def redo_current(self):
        ed = self.tabs.currentWidget()
        if ed:
            ed.redo()

    def select_all_current(self):
        ed = self.tabs.currentWidget()
        if ed:
            ed.selectAll()

    # --- Go to Line ---
    def go_to_line(self):
        ed = self.tabs.currentWidget()
        if not ed:
            return
        max_line = ed.document().blockCount()
        line, ok = QInputDialog.getInt(
            self, "Go to line", f"Line number (1–{max_line}):", min=1, max=max_line
        )
        if ok:
            block = ed.document().findBlockByNumber(line - 1)
            cursor = QTextCursor(block)
            ed.setTextCursor(cursor)
            ed.setFocus()

    # --- Cifrado / Descifrado ---
    def encrypt_current(self):
        ed = self.tabs.currentWidget()
        if ed:
            ed.setPlainText(xor_cipher(ed.toPlainText()))
            self.status.showMessage("Content encrypted (XOR).", 3000)

    def decrypt_current(self):
        ed = self.tabs.currentWidget()
        if ed:
            ed.setPlainText(xor_cipher(ed.toPlainText()))
            self.status.showMessage("Content decrypted (XOR).", 3000)

    # --- Debug sintaxis ---
    def debug_current(self):
        ed = self.tabs.currentWidget()
        if not ed:
            return
        ed.setExtraSelections([])
        self.output.clear()
        code = ed.toPlainText()
        try:
            compile(code, '<string>', 'exec')
            msg = ">>> No syntax errors detected.\n"
            self.status.showMessage("No syntax errors detected.", 5000)
            self.output.appendPlainText(msg)
        except SyntaxError as e:
            ln = e.lineno or 1
            sel = QTextEdit.ExtraSelection()
            sel.format.setBackground(QColor("#FFCCCC"))
            block = ed.document().findBlockByNumber(ln - 1)
            sel.cursor = QTextCursor(block)
            sel.cursor.clearSelection()
            ed.setExtraSelections([sel])
            err = f"SyntaxError en línea {ln}: {e.msg}\n"
            self.status.showMessage(err, 7000)
            self.output.appendPlainText(err)

    # --- Ejecutar código ---
    def run_current(self):
        ed = self.tabs.currentWidget()
        if not ed:
            return
        code = ed.toPlainText()
        tmp = tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w", encoding="utf-8")
        tmp.write(code)
        tmp.close()

        self.output.clear()
        self.status.showMessage("Ejecutando código...", 3000)
        self.proc.start(sys.executable, [tmp.name])

    def handle_stdout(self):
        text = self.proc.readAllStandardOutput().data().decode()
        if text:
            self.output.appendPlainText(text)

    def process_finished(self, exit_code, exit_status):
        self.handle_stdout()
        if exit_code == 0:
            final = ">>> Ejecución completada correctamente, sin errores."
            self.status.showMessage("Proceso finalizado (exit code 0)", 5000)
        else:
            final = f">>> Ejecución finalizada con errores (exit code {exit_code})."
            self.status.showMessage(final, 7000)
        self.output.appendPlainText(final)

    # --- Cerrar pestaña ---
    def close_tab(self, index):
        self.tabs.removeTab(index)
        self.status.showMessage(f"Closed tab {index}", 3000)

# -------------------------------------------------
# Entry point
# -------------------------------------------------
def main():
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
