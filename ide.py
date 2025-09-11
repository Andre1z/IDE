# -*- coding: utf-8 -*-
"""
PyIDE – VSCode Style con:
- Explorador de archivos
- Pestañas de edición (cerrables)
- Resaltado de sintaxis Python (keywords azul, comentarios gris)
- Abrir (simple/múltiple), Guardar, Guardar como
- Encriptar / Desencriptar (XOR)
- Depuración de sintaxis: marca errores de compilación
"""

import sys
import os

from PySide6.QtCore import QDir, QRegularExpression
from PySide6.QtGui import (
    QAction, QColor, QFont,
    QSyntaxHighlighter, QTextCharFormat, QTextCursor
)
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout,
    QTreeView, QFileSystemModel, QTabWidget,
    QPlainTextEdit, QTextEdit, QStatusBar,
    QFileDialog, QMenuBar
)

# -------------------------------------------------
# XOR Cipher
# -------------------------------------------------
ENCRYPTION_KEY = 67

def xor_cipher(text, key=ENCRYPTION_KEY):
    return ''.join(chr(ord(c) ^ key) for c in text)

# -------------------------------------------------
# Syntax Highlighter
# -------------------------------------------------
class PythonHighlighter(QSyntaxHighlighter):
    def __init__(self, doc):
        super().__init__(doc)
        self.rules = []

        # Keywords formato
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
            self.rules.append((pat, kw_fmt))

        # Comentarios formato
        cm_fmt = QTextCharFormat()
        cm_fmt.setForeground(QColor("#888888"))
        cm_pat = QRegularExpression(r"#.*")
        self.rules.append((cm_pat, cm_fmt))

    def highlightBlock(self, text):
        for pattern, fmt in self.rules:
            it = pattern.globalMatch(text)
            while it.hasNext():
                m = it.next()
                self.setFormat(m.capturedStart(), m.capturedLength(), fmt)

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

        # Tabs for editors (cerrables)
        self.tabs = QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.tabCloseRequested.connect(self.close_tab)

        # Layout
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.addWidget(self.tree, 1)
        layout.addWidget(self.tabs, 3)
        self.setCentralWidget(container)

        # Status bar
        self.status = QStatusBar()
        self.setStatusBar(self.status)

        # Menus
        menubar = QMenuBar()
        # File menu
        file_menu = menubar.addMenu("&File")
        file_menu.addAction(self._make_action("Open...", self.open_file))
        file_menu.addAction(self._make_action("Open Multiple...", self.open_multiple))
        file_menu.addSeparator()
        file_menu.addAction(self._make_action("Save", self.save_current))
        file_menu.addAction(self._make_action("Save As...", self.save_as_current))
        file_menu.addSeparator()
        file_menu.addAction(self._make_action("Exit", self.close))
        # Edit menu
        edit_menu = menubar.addMenu("&Edit")
        edit_menu.addAction(self._make_action("Encrypt", self.encrypt_current))
        edit_menu.addAction(self._make_action("Decrypt", self.decrypt_current))
        # Run menu
        run_menu = menubar.addMenu("&Run")
        run_menu.addAction(self._make_action("Debug (Syntax)", self.debug_current))

        self.setMenuBar(menubar)

    def _make_action(self, name, handler):
        act = QAction(name, self)
        act.triggered.connect(handler)
        return act

    def open_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open File", "", "Python Files (*.py);;All Files (*)"
        )
        if path:
            self._load_path(path)

    def open_multiple(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Open Multiple", "", "Python Files (*.py);;All Files (*)"
        )
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
        path, _ = QFileDialog.getSaveFileName(
            self, "Save As", "", "Python Files (*.py);;All Files (*)"
        )
        if not path:
            return
        with open(path, 'w', encoding='utf-8') as f:
            f.write(ed.toPlainText())
        ed.file_path = path
        self.tabs.setTabText(self.tabs.currentIndex(), os.path.basename(path))
        self.status.showMessage(f"Saved As: {path}", 5000)

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

    def close_tab(self, index):
        """Cierra la pestaña indicada por índice."""
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