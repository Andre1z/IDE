# -*- coding: utf-8 -*-
"""
ide.py
PyIDE (todo en un solo archivo, con selector de proyecto al inicio)

Características integradas:
- Diálogo inicial Crear proyecto / Abrir proyecto
- Explorador limitado a la carpeta del proyecto seleccionada
- Pestañas cerrables con resaltado de sintaxis Python
- Open / Open Multiple / New file (inside project)
- Save / Save As (default inside project)
- Encrypt / Decrypt (XOR)
- Debug syntax / Run with Output panel
- Themes, line numbers, auto-indent, tabs, go-to-line, undo/redo
- Estado guardado en estado.json
- Tema por defecto "Default" aplicado al inicio si no hay temas.json
- Forzar texto negro en el árbol para temas claros especificados
"""

import sys
import os
import json
import tempfile
import shutil

from PySide6.QtCore import QDir, QRegularExpression, Qt, QProcess, QRect, QSize, QPoint
from PySide6.QtGui import QAction, QColor, QFont, QSyntaxHighlighter, QTextCharFormat, QTextCursor, QPainter
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout,
    QTreeView, QFileSystemModel, QTabWidget,
    QPlainTextEdit, QStatusBar, QFileDialog, QMenuBar,
    QDockWidget, QInputDialog, QMessageBox,
    QDialog, QVBoxLayout, QLabel, QPushButton, QHBoxLayout as QHLayout,
    QListWidget, QMenu
)

# ---------------------------
# Paths de configuración
# ---------------------------
BASE_DIR = os.path.dirname(__file__)
KW_PATH = os.path.join(BASE_DIR, "palabras_reservadas.json")
THEME_PATH = os.path.join(BASE_DIR, "temas.json")
STATE_PATH = os.path.join(BASE_DIR, "estado.json")

# ---------------------------
# Carga de keywords (si existe)
# ---------------------------
if os.path.exists(KW_PATH):
    try:
        with open(KW_PATH, "r", encoding="utf-8") as f:
            KEYWORDS = json.load(f)
    except Exception:
        KEYWORDS = []
else:
    KEYWORDS = [
        "import", "from", "class", "def", "if", "elif", "else",
        "for", "while", "return", "in", "and", "or", "not",
        "with", "as", "try", "except", "finally", "pass",
        "break", "continue", "yield", "assert", "async", "await",
        "global", "nonlocal", "del", "raise", "is", "lambda"
    ]

# ---------------------------
# Utilidades color
# ---------------------------
def hex_to_rgb(hex_color: str):
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = ''.join(c*2 for c in h)
    r = int(h[0:2], 16)
    g = int(h[2:4], 16)
    b = int(h[4:6], 16)
    return r, g, b

def relative_luminance(hex_color: str) -> float:
    r, g, b = [c / 255.0 for c in hex_to_rgb(hex_color)]
    def chan(c):
        return c/12.92 if c <= 0.03928 else ((c+0.055)/1.055) ** 2.4
    return 0.2126 * chan(r) + 0.7152 * chan(g) + 0.0722 * chan(b)

def is_light(hex_color: str, threshold: float = 0.6) -> bool:
    try:
        lum = relative_luminance(hex_color)
        return lum >= threshold
    except Exception:
        return False

# ---------------------------
# Carga de temas (sin EduDefault) y selección de DEFAULT_THEME
# ---------------------------
if os.path.exists(THEME_PATH):
    try:
        with open(THEME_PATH, "r", encoding="utf-8") as f:
            themes_list = json.load(f)
    except Exception:
        themes_list = []
    THEMES = {t["name"]: t for t in themes_list if "name" in t}
    if "Default" in THEMES:
        DEFAULT_THEME = "Default"
    elif themes_list:
        DEFAULT_THEME = themes_list[0].get("name", next(iter(THEMES), None))
    else:
        THEMES = {}
        DEFAULT_THEME = None
else:
    THEMES = {}
    DEFAULT_THEME = None

# If no themes loaded from file, create a Default theme with requested colors
if not THEMES:
    THEMES = {
        "Default": {
            "name": "Default",
            "background": "#FFFFFF",
            "foreground": "#000000",
            "keyword": "#0066CC",
            "string": "#008000",
            "comment": "#888888",
            "sidebar_background": "#14d69a",
            "terminal_background": "#3d3d3d"
        }
    }
    DEFAULT_THEME = "Default"

# ---------------------------
# Carga de estado previo
# ---------------------------
if os.path.exists(STATE_PATH):
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            STATE = json.load(f)
    except Exception:
        STATE = {"open_files": [], "current_theme": DEFAULT_THEME, "last_dir": ""}
else:
    STATE = {"open_files": [], "current_theme": DEFAULT_THEME, "last_dir": ""}

# ---------------------------
# XOR Cipher
# ---------------------------
ENCRYPTION_KEY = 67
def xor_cipher(text, key=ENCRYPTION_KEY):
    return ''.join(chr(ord(c) ^ key) for c in text)

# ---------------------------
# Line Number Area Widget
# ---------------------------
class LineNumberArea(QWidget):
    def __init__(self, editor):
        super().__init__(editor)
        self.codeEditor = editor

    def sizeHint(self):
        return QSize(self.codeEditor.lineNumberAreaWidth(), 0)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(event.rect(), QColor("#f0f0f0"))
        block = self.codeEditor.firstVisibleBlock()
        block_number = block.blockNumber()
        top = self.codeEditor.blockBoundingGeometry(block).translated(self.codeEditor.contentOffset()).top()
        bottom = top + self.codeEditor.blockBoundingRect(block).height()
        line_height = self.codeEditor.fontMetrics().height()
        painter.setPen(QColor("#888888"))
        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                number = str(block_number + 1)
                painter.drawText(0, top, self.width(), line_height, Qt.AlignRight, number)
            block = block.next()
            top = bottom
            bottom = top + (self.codeEditor.blockBoundingRect(block).height() if block.isValid() else line_height)
            block_number += 1
        painter.end()

# ---------------------------
# Code Editor
# ---------------------------
class CodeEditor(QPlainTextEdit):
    def __init__(self):
        super().__init__()
        space_width = self.fontMetrics().horizontalAdvance(' ')
        self.setTabStopDistance(4 * space_width)
        self.lineNumberArea = LineNumberArea(self)
        self.blockCountChanged.connect(self.updateLineNumberAreaWidth)
        self.updateRequest.connect(self.updateLineNumberArea)
        self.updateLineNumberAreaWidth(0)

    def lineNumberAreaWidth(self):
        digits = len(str(max(1, self.blockCount())))
        return 3 + self.fontMetrics().horizontalAdvance('9') * digits

    def updateLineNumberAreaWidth(self, _):
        self.setViewportMargins(self.lineNumberAreaWidth(), 0, 0, 0)

    def updateLineNumberArea(self, rect, dy):
        if dy:
            self.lineNumberArea.scroll(0, dy)
        else:
            self.lineNumberArea.update(0, rect.y(), self.lineNumberArea.width(), rect.height())
        if rect.contains(self.viewport().rect()):
            self.updateLineNumberAreaWidth(0)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        cr = self.contentsRect()
        self.lineNumberArea.setGeometry(QRect(cr.left(), cr.top(), self.lineNumberAreaWidth(), cr.height()))

    def keyPressEvent(self, event):
        # Auto-indent al pulsar Enter
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            cursor = self.textCursor()
            block = cursor.block()
            text = block.text()
            base_indent = len(text) - len(text.lstrip(' '))
            extra = 4 if text.rstrip().endswith(':') else 0
            super().keyPressEvent(event)
            self.insertPlainText(' ' * (base_indent + extra))
            return
        # Tab = 4 espacios
        if event.key() == Qt.Key_Tab and not event.modifiers():
            self.insertPlainText(' ' * 4)
            return
        # Shift+Tab = des-tabulación
        if event.key() == Qt.Key_Backtab:
            cursor = self.textCursor()
            block = cursor.block()
            text = block.text()
            indent = len(text) - len(text.lstrip(' '))
            if indent >= 4:
                cursor.beginEditBlock()
                start = block.position()
                cursor.setPosition(start)
                cursor.setPosition(start + 4, QTextCursor.KeepAnchor)
                cursor.removeSelectedText()
                cursor.endEditBlock()
            return
        super().keyPressEvent(event)

# ---------------------------
# Syntax Highlighter
# ---------------------------
class PythonHighlighter(QSyntaxHighlighter):
    def __init__(self, doc, theme):
        super().__init__(doc)
        kw_fmt = QTextCharFormat()
        kw_fmt.setForeground(QColor(theme.get("keyword", "#569CD6")))
        kw_fmt.setFontWeight(QFont.Bold)
        self.keyword_rules = [(QRegularExpression(rf"\b{w}\b"), kw_fmt) for w in KEYWORDS]
        self.comment_format = QTextCharFormat()
        self.comment_format.setForeground(QColor(theme.get("comment", "#888888")))
        self.comment_pattern = QRegularExpression(r"#.*")
        self.string_format = QTextCharFormat()
        self.string_format.setForeground(QColor(theme.get("string", "#008000")))
        self.string_pattern = QRegularExpression(r"(['\"]).*?\1")

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
                if not any(start <= s < start + length for start, length in string_spans + comment_spans):
                    self.setFormat(s, l, fmt)

# ---------------------------
# Theme Selection Dialog
# ---------------------------
class ThemeDialog(QDialog):
    def __init__(self, parent, themes, current):
        super().__init__(parent)
        self.setWindowTitle("Seleccionar Tema")
        self.themes = themes
        self.selected = current

        self.list_widget = QListWidget()
        for name in themes:
            self.list_widget.addItem(name)
        idx = list(themes.keys()).index(current) if current in themes else 0
        self.list_widget.setCurrentRow(idx)

        self.preview = QPlainTextEdit()
        self.preview.setReadOnly(True)
        sample = 'def foo():\n    # comentario\n    print("string")\n'
        self.preview.setPlainText(sample)

        btn_apply = QPushButton("Aplicar")
        btn_cancel = QPushButton("Cancelar")
        btn_apply.clicked.connect(self.on_apply)
        btn_cancel.clicked.connect(self.reject)

        hlayout = QHLayout()
        hlayout.addWidget(btn_apply)
        hlayout.addWidget(btn_cancel)

        layout = QVBoxLayout(self)
        layout.addWidget(self.list_widget)
        layout.addWidget(self.preview, 1)
        layout.addLayout(hlayout)

        self.list_widget.currentTextChanged.connect(self.update_preview)
        self.update_preview(self.list_widget.currentItem().text())

    def update_preview(self, name):
        theme = self.themes[name]
        # Determine preview foreground: if background is light, ensure dark text
        bg = theme.get("background", "#ffffff")
        fg = theme.get("foreground", "#000000")
        if is_light(bg):
            fg = "#111111"
        self.preview.setStyleSheet(f"background-color: {bg}; color: {fg};")
        PythonHighlighter(self.preview.document(), theme)

    def on_apply(self):
        self.selected = self.list_widget.currentItem().text()
        self.accept()

# ---------------------------
# Project chooser dialog (integrado)
# ---------------------------
class ProjectDialog(QDialog):
    """
    Dialog modal al inicio para Crear o Abrir proyecto.
    Al aceptar, deja selected_mode ("create"|"open") y selected_path.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Seleccionar proyecto")
        self.setModal(True)
        self.selected_mode = None
        self.selected_path = None

        v = QVBoxLayout()
        v.addWidget(QLabel("<b>¿Crear un proyecto nuevo o abrir uno existente?</b>"))
        btns_layout = QHLayout()
        create_btn = QPushButton("Crear proyecto")
        open_btn = QPushButton("Abrir proyecto")
        cancel_btn = QPushButton("Cancelar")
        create_btn.clicked.connect(self.on_create)
        open_btn.clicked.connect(self.on_open)
        cancel_btn.clicked.connect(self.reject)
        btns_layout.addWidget(create_btn)
        btns_layout.addWidget(open_btn)
        btns_layout.addWidget(cancel_btn)
        v.addLayout(btns_layout)
        v.addWidget(QLabel("Si eliges crear, se te pedirá una carpeta donde inicializar el proyecto."))
        self.setLayout(v)

    def on_create(self):
        folder = QFileDialog.getExistingDirectory(self, "Selecciona carpeta para el proyecto (o crea una nueva)")
        if not folder:
            parent = QFileDialog.getExistingDirectory(self, "Selecciona carpeta padre para crear el proyecto")
            if not parent:
                return
            name, ok = QInputDialog.getText(self, "Nombre del proyecto", "Nombre de la carpeta del proyecto:")
            if not ok or not name.strip():
                return
            folder = os.path.join(parent, name.strip())
            try:
                os.makedirs(folder, exist_ok=True)
            except Exception as ex:
                QMessageBox.warning(self, "Error", f"No se pudo crear la carpeta: {ex}")
                return
        try:
            os.makedirs(folder, exist_ok=True)
        except Exception as ex:
            QMessageBox.warning(self, "Error", f"No se pudo crear la carpeta: {ex}")
            return
        self.selected_mode = "create"
        self.selected_path = folder
        self.accept()

    def on_open(self):
        folder = QFileDialog.getExistingDirectory(self, "Selecciona carpeta del proyecto")
        if not folder:
            return
        self.selected_mode = "open"
        self.selected_path = folder
        self.accept()

# ---------------------------
# Main Window
# ---------------------------
class MainWindow(QMainWindow):
    def __init__(self, project_root=None):
        super().__init__()
        self.setWindowTitle("PyIDE Proyecto")
        self.resize(1024, 768)

        self.project_root = project_root or os.getcwd()
        # File system model limited to project_root
        self.fs_model = QFileSystemModel()
        self.fs_model.setRootPath(self.project_root)
        self.tree = QTreeView()
        self.tree.setModel(self.fs_model)
        self.tree.setRootIndex(self.fs_model.index(self.project_root))
        self.tree.doubleClicked.connect(self.open_from_tree)

        # Context menu setup for tree
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self.on_tree_context_menu)
        # clipboard for copy/paste (store path)
        self._clipboard_path = None
        self._clipboard_is_dir = False

        # Tabs for editors
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

        # Output panel
        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        dock = QDockWidget("Output", self)
        dock.setWidget(self.output)
        self.addDockWidget(Qt.BottomDockWidgetArea, dock)

        # Execution process
        self.proc = QProcess(self)
        self.proc.setProcessChannelMode(QProcess.MergedChannels)
        self.proc.readyReadStandardOutput.connect(self.handle_stdout)
        self.proc.finished.connect(self.process_finished)

        # Menus
        menubar = QMenuBar()
        file_menu = menubar.addMenu("📁 Archivo")
        self.open_act = self._make_action("Abrir archivo...", self.open_file, "Ctrl+O")
        self.open_multi_act = self._make_action("Abrir múltiples...", self.open_multiple)
        self.new_file_act = self._make_action("Nuevo archivo...", self.new_file)
        self.save_act = self._make_action("Guardar", self.save_current, "Ctrl+S")
        self.save_as_act = self._make_action("Guardar como...", self.save_as_current, "Ctrl+Shift+S")
        exit_act = self._make_action("Salir", self.close)
        file_menu.addAction(self.open_act)
        file_menu.addAction(self.open_multi_act)
        file_menu.addAction(self.new_file_act)
        file_menu.addSeparator()
        file_menu.addAction(self.save_act)
        file_menu.addAction(self.save_as_act)
        file_menu.addSeparator()
        file_menu.addAction(exit_act)

        edit_menu = menubar.addMenu("🛠️ Editar")
        edit_menu.addAction(self._make_action("Deshacer", self.undo_current, "Ctrl+Z"))
        edit_menu.addAction(self._make_action("Rehacer", self.redo_current, "Ctrl+Shift+Z"))
        edit_menu.addAction(self._make_action("Seleccionar todo", self.select_all_current, "Ctrl+A"))
        edit_menu.addSeparator()
        self.encrypt_act = self._make_action("Encriptar", self.encrypt_current)
        self.decrypt_act = self._make_action("Desencriptar", self.decrypt_current)
        edit_menu.addAction(self.encrypt_act)
        edit_menu.addAction(self.decrypt_act)
        edit_menu.addSeparator()
        edit_menu.addAction(self._make_action("Ir a línea...", self.go_to_line, "Alt+G"))

        run_menu = menubar.addMenu("🐞 Ejecutar")
        run_menu.addAction(self._make_action("Depurar (sintaxis)", self.debug_current, "Alt+V"))
        run_menu.addAction(self._make_action("Ejecutar (Run)", self.run_current, "F5"))

        settings_menu = menubar.addMenu("⚙️ Ajustes")
        settings_menu.addAction(self._make_action("Temas...", self.open_theme_dialog))

        self.setMenuBar(menubar)

        # Themes and state
        self.state = STATE
        self.themes = THEMES
        # Use saved theme or default determined earlier
        self.current_theme_name = self.state.get("current_theme", DEFAULT_THEME)

        # Track advanced actions to hide in beginner mode
        self.advanced_actions = [self.open_multi_act, self.encrypt_act, self.decrypt_act]
        self._enable_beginner_mode()

        # Ensure project folder exists
        try:
            os.makedirs(self.project_root, exist_ok=True)
        except Exception as ex:
            QMessageBox.warning(self, "Error", f"No se pudo asegurar la carpeta del proyecto: {ex}")

        # Apply theme (this also sets sidebar and output colors)
        self.apply_theme(self.current_theme_name)
        self.status.showMessage(f"Proyecto: {self.project_root}", 5000)

        # Reopen previous files only if they belong to this project
        for path in self.state.get("open_files", []):
            if os.path.isfile(path):
                try:
                    common = os.path.commonpath([os.path.abspath(path), os.path.abspath(self.project_root)])
                except Exception:
                    common = ""
                if common == os.path.abspath(self.project_root):
                    self._load_path(path)

    def _make_action(self, text, handler, shortcut=None):
        act = QAction(text, self)
        act.triggered.connect(handler)
        if shortcut:
            act.setShortcut(shortcut)
        return act

    def _enable_beginner_mode(self):
        for act in self.advanced_actions:
            act.setVisible(False)

    def toggle_advanced(self, checked):
        for act in self.advanced_actions:
            act.setVisible(checked)

    # ----------------------------
    # Tree context menu handlers
    # ----------------------------
    def on_tree_context_menu(self, point: QPoint):
        index = self.tree.indexAt(point)
        model = self.tree.model()

        menu = QMenu(self)

        # Decide target path and whether it's a dir
        if not index.isValid():
            # Click on empty area of the tree
            target_path = self.project_root
            is_dir = True
            create_act = menu.addAction("Crear")
            copy_act = menu.addAction("Copiar")
            paste_act = menu.addAction("Pegar")
            can_copy = False
            if self._clipboard_path:
                can_copy = True
            else:
                ed = self.tabs.currentWidget()
                if ed and hasattr(ed, "file_path") and ed.file_path:
                    can_copy = True
            copy_act.setEnabled(can_copy)
            paste_act.setEnabled(self._clipboard_path is not None)
            create_act.triggered.connect(lambda: self.create_in_folder(target_path))
            copy_act.triggered.connect(self.handle_copy_from_context_when_empty)
            paste_act.triggered.connect(lambda: self.handle_paste(target_path, True))
            menu.exec(self.tree.viewport().mapToGlobal(point))
            return

        # If clicked on an index (file or dir)
        path = model.filePath(index)
        is_dir = os.path.isdir(path)

        # If it's a directory, show Create; if it's a file, do not show Create
        if is_dir:
            create_act = menu.addAction("Crear")
            create_act.triggered.connect(lambda: self.create_in_folder(path))

        copy_act = menu.addAction("Copiar")
        paste_act = menu.addAction("Pegar")
        delete_act = menu.addAction("Eliminar")

        copy_act.setEnabled(True)
        paste_act.setEnabled(self._clipboard_path is not None)

        copy_act.triggered.connect(lambda: self.handle_copy(path, is_dir))
        paste_act.triggered.connect(lambda: self.handle_paste(path, is_dir))
        delete_act.triggered.connect(lambda: self.handle_delete(path, is_dir))

        menu.exec(self.tree.viewport().mapToGlobal(point))

    def handle_copy_from_context_when_empty(self):
        if self._clipboard_path:
            self.status.showMessage(f"Copiado: {self._clipboard_path}", 2000)
            return
        ed = self.tabs.currentWidget()
        if ed and hasattr(ed, "file_path") and ed.file_path:
            self._clipboard_path = ed.file_path
            self._clipboard_is_dir = False
            self.status.showMessage(f"Copiado desde pestaña activa: {self._clipboard_path}", 2000)
        else:
            self.status.showMessage("Nada para copiar (no hay pestaña activa con archivo).", 2000)

    def create_in_folder(self, folder):
        name, ok = QInputDialog.getText(self, "Crear archivo", "Nombre del nuevo archivo (ej. main.py):")
        if not ok or not name.strip():
            return
        name = name.strip()
        target = os.path.join(folder, name)
        if os.path.exists(target):
            QMessageBox.warning(self, "Existe", "El archivo ya existe.")
            return
        try:
            with open(target, 'w', encoding='utf-8') as f:
                f.write("# Nuevo archivo creado desde el menú contextual\n")
            # refresh model and open file
            self.fs_model.refresh()
            self._load_path(target)
            self.status.showMessage(f"Archivo creado: {target}", 3000)
        except Exception as ex:
            QMessageBox.warning(self, "Error", f"No se pudo crear el archivo: {ex}")

    def handle_copy(self, path, is_dir):
        # store path for later paste
        self._clipboard_path = path
        self._clipboard_is_dir = is_dir
        self.status.showMessage(f"Copiado: {path}", 2000)

    def handle_paste(self, path, is_dir):
        # Determine destination folder
        if is_dir:
            dest_folder = path
        else:
            dest_folder = os.path.dirname(path)
        if not self._clipboard_path:
            return
        src = self._clipboard_path
        try:
            if self._clipboard_is_dir:
                base = os.path.basename(src)
                dest = os.path.join(dest_folder, base)
                if os.path.exists(dest):
                    QMessageBox.warning(self, "Existe", "La carpeta destino ya existe.")
                    return
                shutil.copytree(src, dest)
                self.status.showMessage(f"Carpeta pegada en: {dest}", 3000)
            else:
                base = os.path.basename(src)
                dest = os.path.join(dest_folder, base)
                if os.path.exists(dest):
                    name, ext = os.path.splitext(base)
                    i = 1
                    while os.path.exists(dest):
                        dest = os.path.join(dest_folder, f"{name}_{i}{ext}")
                        i += 1
                shutil.copy2(src, dest)
                self.status.showMessage(f"Archivo pegado en: {dest}", 3000)
            self.fs_model.refresh()
        except Exception as ex:
            QMessageBox.warning(self, "Error", f"No se pudo pegar: {ex}")

    def handle_delete(self, path, is_dir):
        confirm = QMessageBox.question(self, "Eliminar", f"¿Eliminar {'carpeta' if is_dir else 'archivo'}?\n{path}", QMessageBox.Yes | QMessageBox.No)
        if confirm != QMessageBox.Yes:
            return
        try:
            if is_dir:
                shutil.rmtree(path)
            else:
                os.remove(path)
            self.fs_model.refresh()
            self.status.showMessage(f"Eliminado: {path}", 3000)
        except Exception as ex:
            QMessageBox.warning(self, "Error", f"No se pudo eliminar: {ex}")

    # ----------------------------
    # Themes
    # ----------------------------
    def open_theme_dialog(self):
        dlg = ThemeDialog(self, self.themes, self.current_theme_name)
        if dlg.exec() == QDialog.Accepted:
            self.apply_theme(dlg.selected)

    def apply_theme(self, theme_name):
        theme = self.themes.get(theme_name, list(self.themes.values())[0])
        self.current_theme_name = theme_name

        # Sidebar / explorer background
        sidebar_color = theme.get("sidebar_background", theme.get("background", "#ffffff"))

        # Lista de temas claros que deben mostrar texto negro en el árbol
        claro_force_black = {"Light", "Solarized Light", "One Light", "Material Light", "Default"}

        # Determinar color de texto del árbol: negro si el tema está en la lista, si no usar foreground del tema
        if theme_name in claro_force_black:
            tree_text_color = "#000000"
        else:
            tree_text_color = theme.get("foreground", "#ffffff")
            sb_bg = sidebar_color
            try:
                if is_light(sb_bg):
                    tree_text_color = "#000000"
            except Exception:
                pass

        # Aplicar estilo al árbol (background + color del texto de los elementos)
        try:
            self.tree.setStyleSheet(f"background-color: {sidebar_color}; color: {tree_text_color};")
        except Exception:
            pass

        # Determine editor foreground: if editor background is light, use dark text
        editor_bg = theme.get("background", "#ffffff")
        editor_fg = theme.get("foreground", "#000000")
        if is_light(editor_bg):
            editor_fg = "#111111"

        # Editors
        for i in range(self.tabs.count()):
            ed = self.tabs.widget(i)
            ed.setStyleSheet(f"background-color: {editor_bg}; color: {editor_fg};")
            PythonHighlighter(ed.document(), theme)

        # Output / terminal background and foreground
        term_bg = theme.get("terminal_background", theme.get("background", "#ffffff"))
        if is_light(term_bg):
            term_fg = "#111111"
        else:
            term_fg = "#ffffff"
        self.output.setStyleSheet(f"background-color: {term_bg}; color: {term_fg};")

    # -----------------------
    # Open / Save (limited to project)
    # -----------------------
    def open_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Abrir archivo", self.project_root, "Python Files (*.py);;All Files (*)")
        if path:
            STATE["last_dir"] = os.path.dirname(path)
            self._load_path(path)

    def open_multiple(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "Abrir múltiples", self.project_root, "Python Files (*.py);;All Files (*)")
        for p in paths:
            STATE["last_dir"] = os.path.dirname(p)
            self._load_path(p)

    def open_from_tree(self, idx):
        path = self.fs_model.filePath(idx)
        if os.path.isfile(path):
            self._load_path(path)

    def _load_path(self, path):
        try:
            common = os.path.commonpath([os.path.abspath(path), os.path.abspath(self.project_root)])
        except Exception:
            common = ""
        if common != os.path.abspath(self.project_root):
            QMessageBox.warning(self, "Fuera del proyecto", "Solo puedes abrir archivos dentro de la carpeta del proyecto.")
            return
        try:
            with open(path, 'r', encoding='utf-8') as f:
                text = f.read()
        except Exception as ex:
            QMessageBox.warning(self, "Error", f"No se pudo abrir el archivo: {ex}")
            return
        editor = CodeEditor()
        editor.setPlainText(text)
        editor.file_path = path
        editor.document().setModified(False)

        # Apply current theme colors to this editor (respecting light/dark fg logic)
        theme = self.themes.get(self.current_theme_name, list(self.themes.values())[0])
        editor_bg = theme.get("background", "#ffffff")
        editor_fg = theme.get("foreground", "#000000")
        if is_light(editor_bg):
            editor_fg = "#111111"
        editor.setStyleSheet(f"background-color: {editor_bg}; color: {editor_fg};")

        PythonHighlighter(editor.document(), theme)
        title = os.path.basename(path)
        self.tabs.addTab(editor, title)
        self.status.showMessage(f"Abriste: {path}", 3000)

    def save_current(self):
        ed = self.tabs.currentWidget()
        if not ed:
            return
        if not hasattr(ed, "file_path") or not ed.file_path:
            return self.save_as_current(default_dir=self.project_root)
        try:
            with open(ed.file_path, 'w', encoding='utf-8') as f:
                f.write(ed.toPlainText())
            ed.document().setModified(False)
            self.status.showMessage(f"Guardado: {ed.file_path}", 3000)
        except Exception as ex:
            QMessageBox.warning(self, "Error", f"No se pudo guardar: {ex}")

    def save_as_current(self, default_dir=None):
        ed = self.tabs.currentWidget()
        if not ed:
            return
        start_dir = default_dir or STATE.get("last_dir", self.project_root)
        path, _ = QFileDialog.getSaveFileName(self, "Guardar como", start_dir, "Python Files (*.py);;All Files (*)")
        if not path:
            return
        try:
            with open(path, 'w', encoding='utf-8') as f:
                f.write(ed.toPlainText())
            ed.file_path = path
            ed.document().setModified(False)
            self.tabs.setTabText(self.tabs.currentIndex(), os.path.basename(path))
            STATE["last_dir"] = os.path.dirname(path)
            self.status.showMessage(f"Guardado como: {path}", 3000)
        except Exception as ex:
            QMessageBox.warning(self, "Error", f"No se pudo guardar: {ex}")

    # -----------------------
    # Edit helpers
    # -----------------------
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

    def go_to_line(self):
        ed = self.tabs.currentWidget()
        if not ed:
            return
        max_line = ed.document().blockCount()
        line, ok = QInputDialog.getInt(self, "Ir a línea", f"Line number (1–{max_line}):", 1, 1, max_line, 1)
        if ok:
            block = ed.document().findBlockByNumber(line - 1)
            cursor = QTextCursor(block)
            ed.setTextCursor(cursor)
            ed.setFocus()

    # -----------------------
    # New file (inside project)
    # -----------------------
    def new_file(self):
        base_name = "nuevo.py"
        i = 1
        candidate = os.path.join(self.project_root, base_name)
        while os.path.exists(candidate):
            candidate = os.path.join(self.project_root, f"nuevo{i}.py")
            i += 1
        try:
            with open(candidate, 'w', encoding='utf-8') as f:
                f.write("# Nuevo archivo\n\n")
        except Exception as ex:
            QMessageBox.warning(self, "Error", f"No se pudo crear el archivo: {ex}")
            return
        self._load_path(candidate)

    # -----------------------
    # Encrypt / Decrypt
    # -----------------------
    def encrypt_current(self):
        ed = self.tabs.currentWidget()
        if ed:
            ed.setPlainText(xor_cipher(ed.toPlainText()))
            self.status.showMessage("Contenido encriptado (XOR).", 3000)

    def decrypt_current(self):
        ed = self.tabs.currentWidget()
        if ed:
            ed.setPlainText(xor_cipher(ed.toPlainText()))
            self.status.showMessage("Contenido desencriptado (XOR).", 3000)

    # -----------------------
    # Debug syntax
    # -----------------------
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
            from PySide6.QtWidgets import QTextEdit
            sel = QTextEdit.ExtraSelection()
            sel.format.setBackground(QColor("#FFCCCC"))
            block = ed.document().findBlockByNumber(ln - 1)
            sel.cursor = QTextCursor(block)
            sel.cursor.clearSelection()
            ed.setExtraSelections([sel])
            err = f"SyntaxError en línea {ln}: {e.msg}\n"
            self.status.showMessage(err, 7000)
            self.output.appendPlainText(err)

    # -----------------------
    # Run code
    # -----------------------
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

    # -----------------------
    # Close tab
    # -----------------------
    def close_tab(self, index):
        self.tabs.removeTab(index)
        self.status.showMessage("Pestaña cerrada", 2000)

    # -----------------------
    # Close event (save state)
    # -----------------------
    def closeEvent(self, event):
        # verificar cambios sin guardar
        unsaved = []
        for i in range(self.tabs.count()):
            ed = self.tabs.widget(i)
            if hasattr(ed, "file_path") and ed.document().isModified():
                unsaved.append((i, ed))
        if unsaved:
            dlg = QMessageBox(self)
            dlg.setIcon(QMessageBox.Warning)
            dlg.setText("Hay cambios sin guardar.")
            dlg.setInformativeText("¿Qué deseas hacer?")
            dlg.setStandardButtons(QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel)
            dlg.button(QMessageBox.Save).setText("Guardar y Cerrar")
            dlg.button(QMessageBox.Discard).setText("Cerrar sin guardar")
            dlg.button(QMessageBox.Cancel).setText("Cancelar")
            resp = dlg.exec()
            if resp == QMessageBox.Cancel:
                event.ignore()
                return
            if resp == QMessageBox.Save:
                for idx, _ in unsaved:
                    self.tabs.setCurrentIndex(idx)
                    self.save_current()
        # guardar estado (solo archivos dentro del proyecto)
        open_files = []
        for i in range(self.tabs.count()):
            ed = self.tabs.widget(i)
            if hasattr(ed, "file_path"):
                try:
                    common = os.path.commonpath([os.path.abspath(ed.file_path), os.path.abspath(self.project_root)])
                except Exception:
                    common = ""
                if common == os.path.abspath(self.project_root):
                    open_files.append(ed.file_path)
        self.state["open_files"] = open_files
        self.state["current_theme"] = self.current_theme_name
        try:
            with open(STATE_PATH, "w", encoding="utf-8") as f:
                json.dump(self.state, f, indent=2)
        except Exception:
            pass
        event.accept()

# ---------------------------
# Entry point with Project Dialog
# ---------------------------
def main():
    app = QApplication(sys.argv)

    # Project selector dialog at startup
    dlg = ProjectDialog()
    result = dlg.exec()
    if result != QDialog.Accepted:
        cont = QMessageBox.question(None, "Continuar sin proyecto",
                                    "No se seleccionó proyecto. ¿Quieres continuar sin proyecto? Se usará la carpeta actual.",
                                    QMessageBox.Yes | QMessageBox.No)
        if cont == QMessageBox.No:
            sys.exit(0)
        project_root = os.getcwd()
    else:
        project_root = dlg.selected_path
        if dlg.selected_mode == "create":
            main_py = os.path.join(project_root, "main.py")
            if not os.path.exists(main_py):
                try:
                    with open(main_py, 'w', encoding='utf-8') as f:
                        f.write(
                            "# main.py - archivo inicial del proyecto\n\n"
                            "def main():\n"
                            "    print('Hola desde el proyecto')\n\n"
                            "if __name__ == '__main__':\n"
                            "    main()\n"
                        )
                except Exception:
                    pass

    win = MainWindow(project_root=project_root)
    win.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
