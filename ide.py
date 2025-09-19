# -*- coding: utf-8 -*-
"""
PyIDE – VSCode Style con:
- Explorador de archivos
- Pestañas de edición (cerrables)
- Resaltado de sintaxis Python (keywords azul, strings rojo, comentarios gris)
- Abrir (simple/múltiple), Guardar, Guardar como
- Encriptar / Desencriptar (XOR)
- Depuración de sintaxis: marca errores de compilación
- Ejecutar código Python y mostrar salida
"""

import sys
import os
import tempfile

from PySide6.QtCore import (
    QDir, QRegularExpression, Qt, QProcess
)
from PySide6.QtGui import (
    QAction, QColor, QFont,
    QSyntaxHighlighter, QTextCharFormat, QTextCursor
)
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout,
    QTreeView, QFileSystemModel, QTabWidget,
    QPlainTextEdit, QStatusBar,
    QFileDialog, QMenuBar, QDockWidget
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

        # Formato keywords
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

        # Formato comentarios
        self.comment_pattern = QRegularExpression(r"#.*")
        self.comment_format = QTextCharFormat()
        self.comment_format.setForeground(QColor("#888888"))

        # Formato strings (simples, no-multilínea)
        self.string_pattern = QRegularExpression(r"(['\"]).*?\1")
        self.string_format = QTextCharFormat()
        self.string_format.setForeground(QColor("#A31515"))

    def highlightBlock(self, text):
        # 1) localizar y pintar strings
        string_spans = []
        it = self.string_pattern.globalMatch(text)
        while it.hasNext():
            m = it.next()
            s, l = m.capturedStart(), m.capturedLength()
            self.setFormat(s, l, self.string_format)
            string_spans.append((s, l))

        # 2) localizar y pintar comentarios
        comment_spans = []
        it = self.comment_pattern.globalMatch(text)
        while it.hasNext():
            m = it.next()
            s, l = m.capturedStart(), m.capturedLength()
            self.setFormat(s, l, self.comment_format)
            comment_spans.append((s, l))

        # 3) pintar keywords sólo fuera de strings/comentarios
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

        # File system tree
        model = QFileSystemModel()
        model.setRootPath(QDir.currentPath())
        self.tree = QTreeView()
        self.tree.setModel(model)
        self.tree.setRootIndex(model.index(QDir.currentPath()))
        self.tree.doubleClicked.connect(self.open_from_tree)

        # Tabs para editores
        self.tabs = QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.tabCloseRequested.connect(self.close_tab)

        # Layout central: árbol + tabs
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.addWidget(self.tree, 1)
        layout.addWidget(self.tabs, 3)
        self.setCentralWidget(container)

        # Status bar
        self.status = QStatusBar()
        self.setStatusBar(self.status)

        # Panel de salida (dockable)
        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        dock = QDockWidget("Output", self)
        dock.setWidget(self.output)
        self.addDockWidget(Qt.BottomDockWidgetArea, dock)

        # QProcess para ejecución
        self.proc = QProcess(self)
        self.proc.setProcessChannelMode(QProcess.MergedChannels)
        self.proc.readyReadStandardOutput.connect(self.handle_stdout)
        self.proc.finished.connect(self.process_finished)

        # Menús
        menubar = QMenuBar()
        # File
        file_menu = menubar.addMenu("&File")
        file_menu.addAction(self._make_action("Open...", self.open_file))
        file_menu.addAction(self._make_action("Open Multiple...", self.open_multiple))
        file_menu.addSeparator()
        file_menu.addAction(self._make_action("Save", self.save_current))
        file_menu.addAction(self._make_action("Save As...", self.save_as_current))
        file_menu.addSeparator()
        file_menu.addAction(self._make_action("Exit", self.close))
        # Edit
        edit_menu = menubar.addMenu("&Edit")
        edit_menu.addAction(self._make_action("Encrypt", self.encrypt_current))
        edit_menu.addAction(self._make_action("Decrypt", self.decrypt_current))
        # Run
        run_menu = menubar.addMenu("&Run")
        run_menu.addAction(self._make_action("Debug (Syntax)", self.debug_current))
        run_menu.addAction(self._make_action("Run Code", self.run_current))

        self.setMenuBar(menubar)

    def _make_action(self, name, handler):
        act = QAction(name, self)
        act.triggered.connect(handler)
        return act

    # --- abrir/guardar ---
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

    # --- cifrado/descifrado ---
    def encrypt_current(self):
        ed = self.tabs.currentWidget()
        txt = ed.toPlainText()
        ed.setPlainText(xor_cipher(txt))
        self.status.showMessage("Content encrypted (XOR).", 3000)

    def decrypt_current(self):
        ed = self.tabs.currentWidget()
        txt = ed.toPlainText()
        ed.setPlainText(xor_cipher(txt))
        self.status.showMessage("Content decrypted (XOR).", 3000)

    # --- debug sintaxis ---
    def debug_current(self):
        ed = self.tabs.currentWidget()
        ed.setExtraSelections([])
        code = ed.toPlainText()
        try:
            compile(code, '<string>', 'exec')
            self.status.showMessage("No syntax errors detected.", 5000)
        except SyntaxError as e:
            ln = e.lineno or 1
            sel = QTextEdit.ExtraSelection()
            sel.format.setBackground(QColor("#FFCCCC"))
            block = ed.document().findBlockByNumber(ln - 1)
            sel.cursor = QTextCursor(block)
            sel.cursor.clearSelection()
            ed.setExtraSelections([sel])
            self.status.showMessage(f"Syntax error at line {ln}: {e.msg}", 7000)

    # --- ejecutar código ---
    def run_current(self):
        ed = self.tabs.currentWidget()
        if not ed:
            return
        # volcamos el código a un temp file
        code = ed.toPlainText()
        tmp = tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w", encoding="utf-8")
        tmp.write(code)
        tmp.flush()
        tmp.close()

        self.output.clear()
        self.status.showMessage("Executing...", 3000)
        # arrancamos QProcess
        self.proc.start(sys.executable, [tmp.name])

    def handle_stdout(self):
        data = self.proc.readAllStandardOutput().data().decode()
        self.output.appendPlainText(data)

    def process_finished(self, code, status):
        self.status.showMessage(f"Process finished (exit code {code})", 5000)

    # --- cerrar pestaña ---
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
