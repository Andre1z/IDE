# -*- coding: utf-8 -*-
"""
PyIDE Educativo – selector de proyecto al inicio
- Al iniciar pide Crear proyecto o Abrir proyecto
- Explorador limitado a la carpeta del proyecto seleccionada
- Crear proyecto crea carpeta y archivo main.py si no existe
- Mantiene: pestañas cerrables, resaltado, abrir/guardar, encriptar, depurar
"""

import sys, os
from PySide6.QtCore import QDir, QRegularExpression, Qt
from PySide6.QtGui import (
    QAction, QColor, QFont,
    QSyntaxHighlighter, QTextCharFormat, QTextCursor
)
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout,
    QTreeView, QFileSystemModel, QTabWidget,
    QPlainTextEdit, QStatusBar, QFileDialog,
    QMenuBar, QDockWidget, QTextBrowser, QMessageBox,
    QDialog, QVBoxLayout, QLabel, QPushButton, QHBoxLayout as QHLayout
)

# -------------------------------------------------
# XOR Cipher
# -------------------------------------------------
ENCRYPTION_KEY = 67
def xor_cipher(text, key=ENCRYPTION_KEY):
    return ''.join(chr(ord(c) ^ key) for c in text)

# -------------------------------------------------
# Python Syntax Highlighter
# -------------------------------------------------
class PythonHighlighter(QSyntaxHighlighter):
    def __init__(self, document):
        super().__init__(document)
        self.rules = []
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
# Project chooser dialog
# -------------------------------------------------
class ProjectDialog(QDialog):
    """
    Dialog modal shown at startup to choose Create or Open Project.
    Returns tuple (mode, path) where mode in {"create","open"} and path is folder path or None.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Seleccionar proyecto")
        self.setModal(True)
        self.selected_mode = None
        self.selected_path = None

        v = QVBoxLayout()
        v.addWidget(QLabel("<b>¿Crear un proyecto nuevo o abrir uno existente?</b>"))

        # Buttons
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
            # allow user to create folder by selecting parent and prompt for folder name
            parent = QFileDialog.getExistingDirectory(self, "Selecciona carpeta padre para crear el proyecto")
            if not parent:
                return
            # ask for folder name using a simple input dialog
            from PySide6.QtWidgets import QInputDialog
            name, ok = QInputDialog.getText(self, "Nombre del proyecto", "Nombre de la carpeta del proyecto:")
            if not ok or not name.strip():
                return
            folder = os.path.join(parent, name.strip())
            try:
                os.makedirs(folder, exist_ok=True)
            except Exception as ex:
                QMessageBox.warning(self, "Error", f"No se pudo crear la carpeta: {ex}")
                return
        # Ensure folder exists
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

# -------------------------------------------------
# Main Window
# -------------------------------------------------
class MainWindow(QMainWindow):
    def __init__(self, project_root=None):
        super().__init__()
        self.setWindowTitle("PyIDE Educativo – Proyecto")
        self.resize(1024, 768)

        # Store project root (folder) which limits the explorer and default save location
        self.project_root = project_root or os.getcwd()

        # File system explorer (limited to project_root)
        self.fs_model = QFileSystemModel()
        # setFilter to show files and dirs (default)
        self.fs_model.setRootPath(self.project_root)
        self.tree = QTreeView()
        self.tree.setModel(self.fs_model)
        self.tree.setRootIndex(self.fs_model.index(self.project_root))
        self.tree.doubleClicked.connect(self.open_from_tree)

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

        # Help dock
        self.help_dock = QDockWidget("🛈 Ayuda", self)
        self.help_panel = QTextBrowser()
        self.help_panel.setHtml(
            "<h3>Guía Rápida</h3>"
            "<ul>"
            "<li><b>Abrir:</b> Ctrl+O – Carga un archivo .py en el proyecto</li>"
            "<li><b>Guardar:</b> Ctrl+S – Guarda en la carpeta del proyecto</li>"
            "<li><b>Depurar:</b> Ctrl+D – Marca errores de sintaxis</li>"
            "<li><b>Ejemplo nuevo:</b> Carga plantilla básica</li>"
            "</ul>"
        )
        self.help_dock.setWidget(self.help_panel)
        self.addDockWidget(Qt.RightDockWidgetArea, self.help_dock)

        # Menus
        menubar = QMenuBar()
        file_menu = menubar.addMenu("📁 Archivo")
        self.open_act = self._make_action("Abrir archivo...", self.open_file, "Ctrl+O", "Abrir un archivo Python dentro del proyecto")
        self.open_multi_act = self._make_action("Abrir múltiples...", self.open_multiple, None, "Abrir varios archivos")
        self.new_file_act = self._make_action("Nuevo archivo...", self.new_file, None, "Crear un nuevo archivo dentro del proyecto")
        self.save_act = self._make_action("Guardar", self.save_current, "Ctrl+S", "Guardar el archivo actual (en la carpeta del proyecto)")
        self.save_as_act = self._make_action("Guardar como...", self.save_as_current, None, "Guardar con nuevo nombre")
        exit_act = self._make_action("Salir", self.close, None, "Salir del IDE")
        file_menu.addAction(self.open_act)
        file_menu.addAction(self.open_multi_act)
        file_menu.addAction(self.new_file_act)
        file_menu.addSeparator()
        file_menu.addAction(self.save_act)
        file_menu.addAction(self.save_as_act)
        file_menu.addSeparator()
        file_menu.addAction(exit_act)

        edit_menu = menubar.addMenu("🛠️ Editar")
        self.encrypt_act = self._make_action("Encriptar", self.encrypt_current, None, "Encriptar contenido (XOR)")
        self.decrypt_act = self._make_action("Desencriptar", self.decrypt_current, None, "Desencriptar contenido (XOR)")
        example_act = self._make_action("Ejemplo nuevo", self.new_example, None, "Cargar plantilla básica de Python")
        edit_menu.addAction(self.encrypt_act)
        edit_menu.addAction(self.decrypt_act)
        edit_menu.addAction(example_act)

        run_menu = menubar.addMenu("🐞 Ejecutar")
        self.debug_act = self._make_action("Depurar (sintaxis)", self.debug_current, "Ctrl+D", "Marcar errores de sintaxis")
        run_menu.addAction(self.debug_act)

        view_menu = menubar.addMenu("👁️ Vista")
        self.toggle_adv_act = QAction("Mostrar funciones avanzadas", self, checkable=True)
        self.toggle_adv_act.setToolTip("Mostrar u ocultar opciones avanzadas")
        self.toggle_adv_act.triggered.connect(self.toggle_advanced)
        view_menu.addAction(self.toggle_adv_act)

        self.setMenuBar(menubar)

        # Track advanced actions to hide in beginner mode
        self.advanced_actions = [self.open_multi_act, self.encrypt_act, self.decrypt_act]

        # Begin in beginner mode
        self._enable_beginner_mode()

        # If project_root provided, ensure it has a main.py when created
        if not os.path.isdir(self.project_root):
            try:
                os.makedirs(self.project_root, exist_ok=True)
            except Exception as ex:
                QMessageBox.warning(self, "Error", f"No se pudo crear la carpeta del proyecto: {ex}")

        # Show initial project root in status
        self.status.showMessage(f"Proyecto: {self.project_root}", 5000)

    def _make_action(self, text, handler, shortcut=None, tooltip=None):
        act = QAction(text, self)
        act.triggered.connect(handler)
        if shortcut:
            act.setShortcut(shortcut)
        if tooltip:
            act.setToolTip(tooltip)
        return act

    def _enable_beginner_mode(self):
        for act in self.advanced_actions:
            act.setVisible(False)
        self.toggle_adv_act.setChecked(False)

    def toggle_advanced(self, checked):
        for act in self.advanced_actions:
            act.setVisible(checked)

    # ----------------------------
    # Project & files operations
    # ----------------------------
    def new_example(self):
        code = (
            "# Ejemplo básico de Python\n"
            "# Declaración de variable, condicional, función main\n\n"
            "def main():\n"
            "    contador = 3  # Declaración y asignación\n"
            "    mensaje = \"¡Hola desde PyIDE!\"\n"
            "    if contador > 0:\n"
            "        print(mensaje)\n"
            "    else:\n"
            "        print(\"Contador llegó a cero.\")\n\n"
            "if __name__ == \"__main__\":\n"
            "    main()\n"
        )
        editor = QPlainTextEdit()
        editor.setPlainText(code)
        editor.file_path = None
        PythonHighlighter(editor.document())
        self.tabs.addTab(editor, "Ejemplo.py")
        self.status.showMessage("Ejemplo cargado", 3000)

    def _load_path(self, path):
        # Only allow files inside project_root
        if not os.path.commonpath([os.path.abspath(path), os.path.abspath(self.project_root)]) == os.path.abspath(self.project_root):
            QMessageBox.warning(self, "Fuera del proyecto", "Solo puedes abrir archivos dentro de la carpeta del proyecto.")
            return
        try:
            with open(path, 'r', encoding='utf-8') as f:
                text = f.read()
        except Exception as ex:
            QMessageBox.warning(self, "Error", f"No se pudo abrir el archivo: {ex}")
            return
        editor = QPlainTextEdit()
        editor.setPlainText(text)
        editor.file_path = path
        PythonHighlighter(editor.document())
        title = os.path.basename(path)
        self.tabs.addTab(editor, title)
        self.status.showMessage(f"Abriste: {path}", 3000)

    def open_file(self):
        # Default location: project_root
        path, _ = QFileDialog.getOpenFileName(
            self, "Abrir archivo", self.project_root, "Python Files (*.py);;All Files (*)"
        )
        if path:
            self._load_path(path)

    def open_multiple(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Abrir múltiples", self.project_root, "Python Files (*.py);;All Files (*)"
        )
        for p in paths:
            self._load_path(p)

    def open_from_tree(self, index):
        path = self.fs_model.filePath(index)
        if os.path.isfile(path):
            self._load_path(path)

    def new_file(self):
        # Create new unsaved file with default name proposal inside project
        base_name = "nuevo.py"
        i = 1
        candidate = os.path.join(self.project_root, base_name)
        while os.path.exists(candidate):
            candidate = os.path.join(self.project_root, f"nuevo{i}.py")
            i += 1
        # create an empty file on disk and open it
        try:
            with open(candidate, 'w', encoding='utf-8') as f:
                f.write("# Nuevo archivo\n")
        except Exception as ex:
            QMessageBox.warning(self, "Error", f"No se pudo crear el archivo: {ex}")
            return
        self._load_path(candidate)

    def save_current(self):
        ed = self.tabs.currentWidget()
        if not ed:
            return
        # If file has associated path, save there; else default to project_root Save As
        if not hasattr(ed, 'file_path') or not ed.file_path:
            return self.save_as_current(default_dir=self.project_root)
        try:
            with open(ed.file_path, 'w', encoding='utf-8') as f:
                f.write(ed.toPlainText())
            self.status.showMessage(f"Guardado: {ed.file_path}", 3000)
        except Exception as ex:
            QMessageBox.warning(self, "Error", f"No se pudo guardar: {ex}")

    def save_as_current(self, default_dir=None):
        ed = self.tabs.currentWidget()
        if not ed:
            return
        start_dir = default_dir or self.project_root
        path, _ = QFileDialog.getSaveFileName(
            self, "Guardar como", start_dir, "Python Files (*.py);;All Files (*)"
        )
        if not path:
            return
        try:
            with open(path, 'w', encoding='utf-8') as f:
                f.write(ed.toPlainText())
            ed.file_path = path
            self.tabs.setTabText(self.tabs.currentIndex(), os.path.basename(path))
            self.status.showMessage(f"Guardado como: {path}", 3000)
        except Exception as ex:
            QMessageBox.warning(self, "Error", f"No se pudo guardar: {ex}")

    # ----------------------------
    # Utilities: encrypt/decrypt/debug/close
    # ----------------------------
    def encrypt_current(self):
        ed = self.tabs.currentWidget()
        if not ed:
            return
        ed.setPlainText(xor_cipher(ed.toPlainText()))
        self.status.showMessage("Contenido encriptado", 3000)

    def decrypt_current(self):
        ed = self.tabs.currentWidget()
        if not ed:
            return
        ed.setPlainText(xor_cipher(ed.toPlainText()))
        self.status.showMessage("Contenido desencriptado", 3000)

    def debug_current(self):
        ed = self.tabs.currentWidget()
        if not ed:
            return
        ed.setExtraSelections([])
        code = ed.toPlainText()
        try:
            compile(code, '<string>', 'exec')
            self.status.showMessage("✅ Sin errores de sintaxis", 3000)
        except SyntaxError as e:
            ln = e.lineno or 1
            sel = QTextEdit.ExtraSelection()
            sel.format.setBackground(QColor("#FFCCCC"))
            block = ed.document().findBlockByNumber(ln - 1)
            sel.cursor = QTextCursor(block)
            sel.cursor.clearSelection()
            ed.setExtraSelections([sel])
            msg = f"❌ Error en línea {ln}: {e.msg}"
            if "expected ':'" in e.msg:
                msg += " → ¿Olvidaste el ':'?"
            elif "unexpected EOF" in e.msg:
                msg += " → ¿Falta cerrar paréntesis o comillas?"
            QMessageBox.warning(self, "Depuración", msg)
            self.status.showMessage(msg, 5000)

    def close_tab(self, index):
        self.tabs.removeTab(index)
        self.status.showMessage("Pestaña cerrada", 2000)

# -------------------------------------------------
# Entry point with Project Dialog
# -------------------------------------------------
def main():
    app = QApplication(sys.argv)

    # Show project selector dialog on first run
    dlg = ProjectDialog()
    result = dlg.exec()
    if result != QDialog.Accepted:
        # user cancelled: ask if they want to continue without project
        cont = QMessageBox.question(None, "Continuar sin proyecto",
                                     "No se seleccionó proyecto. ¿Quieres continuar sin proyecto? "
                                     "Se usará la carpeta actual.",
                                     QMessageBox.Yes | QMessageBox.No)
        if cont == QMessageBox.No:
            sys.exit(0)
        project_root = os.getcwd()
    else:
        project_root = dlg.selected_path
        # If user created a project, ensure there is a main.py template
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
                except Exception as ex:
                    QMessageBox.warning(None, "Error", f"No se pudo crear main.py: {ex}")

    # Launch main window with selected project_root
    win = MainWindow(project_root=project_root)
    win.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()