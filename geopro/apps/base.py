import os
import threading

import requests
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QPushButton, QLineEdit,
    QFileDialog, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QCheckBox, QHeaderView, QApplication, QSplitter, QStatusBar, QMainWindow
)
from PyQt5.QtCore import Qt, QTimer, QSize, QThread, pyqtSignal
from PyQt5.QtGui import QColor, QMovie, QPalette
from pathlib import Path

import qdarktheme

from geopro.core import FileTypeConfig, RunStates
from geopro.config import package_path, Animations, RunningConfig, Themes, AnimationStates, ColorRole, Colors
from geopro.log import setup_logging

log = setup_logging()



class BaseGeoProApp(QMainWindow):
    """
    Fully reusable base class for file-based scraping apps.
    No scraper-specific logic lives here.
    """

    # -------- override in subclasses --------
    WINDOW_TITLE = "Scraper"
    WINDOW_GEOMETRY = (650, 850)

    INPUT_FILE_TYPES = []
    OUTPUT_FILE_TYPES = []

    TABLE_HEADERS = [
        "File Name",
        "# Total Places",
        "# Successful",
        "# Incomplete",
        "Finished"
    ]

    # ---------------------------------------

    def __init__(self):
        super().__init__()

        self.source_type = None
        self.source_files = None
        self.target_location = None
        self.overwrite_target = False
        self.run_headless = False
        self.run_state = None
        self.file_row_map = {}
        self.thread_execution = None
        self.row_colors = None

        self._init_window()
        self.init_ui_base()


    # ------------------------------------------------------------------
    # Initialization
    # ------------------------------------------------------------------

    def _init_window(self):
        self.setWindowTitle(self.WINDOW_TITLE)
        self.setGeometry(2400, 200, *self.WINDOW_GEOMETRY)

    def init_ui_default(self):
        self.init_ui_source_selection()
        self.init_ui_target_selection()
        self.init_ui_options()
        self.init_ui_progress_table()
        self.init_ui_execution_controls()

    def init_ui_base(self):
        # --- Central widget ---
        self.central_widget = QWidget(self)
        self.setCentralWidget(self.central_widget)

        # --- Layout on central widget ---
        self.main_layout = QVBoxLayout(self.central_widget)

        # Left: existing UI
        self.left_panel = QWidget()
        self.left_layout = QVBoxLayout(self.left_panel)

        # Right: map + table
        self.right_panel = QWidget()
        self.right_layout = QVBoxLayout(self.right_panel)

        # splitter
        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.addWidget(self.left_panel)
        self.splitter.addWidget(self.right_panel)
        self.splitter.setSizes([600,500])

        self.main_layout.addWidget(self.splitter)

    def init_ui_source_selection(self):
        self.source_label = QLabel("Select Source:")

        self.browse_files_btn = QPushButton("Files")
        self.browse_files_btn.clicked.connect(self.select_source_files)

        self.browse_folder_btn = QPushButton("Folder")
        self.browse_folder_btn.clicked.connect(self.select_source_folder)

        self.source_entry = QLineEdit()
        self.source_entry.setReadOnly(True)

        btns = QHBoxLayout()
        btns.addWidget(self.browse_files_btn)
        btns.addWidget(self.browse_folder_btn)

        self.left_layout.addWidget(self.source_label)
        self.left_layout.addLayout(btns)
        self.left_layout.addWidget(self.source_entry)
        self.left_layout.addSpacing(20)

    def init_ui_target_selection(self):
        self.target_label = QLabel("Select Target:")

        self.browse_target_file_btn = QPushButton("File")
        self.browse_target_file_btn.clicked.connect(self.select_target_file)

        self.browse_target_folder_btn = QPushButton("Folder")
        self.browse_target_folder_btn.clicked.connect(self.select_target_folder)

        self.target_entry = QLineEdit()
        self.target_entry.setReadOnly(True)

        btns = QHBoxLayout()
        btns.addWidget(self.browse_target_file_btn)
        btns.addWidget(self.browse_target_folder_btn)

        self.left_layout.addWidget(self.target_label)
        self.left_layout.addLayout(btns)
        self.left_layout.addWidget(self.target_entry)

        self.left_layout.addSpacing(20)

    def init_ui_options(self):
        self.options_label = QLabel("Options:")

        layout = QHBoxLayout()

        self.overwrite_checkbox = QCheckBox("Overwrite existing targets")
        self.overwrite_checkbox.stateChanged.connect(
            lambda s: setattr(self, "overwrite_target", s == Qt.Checked)
        )

        self.headless_checkbox = QCheckBox("Run headless")
        self.headless_checkbox.stateChanged.connect(
            lambda s: setattr(self, "run_headless", s == Qt.Checked)
        )

        layout.addWidget(self.overwrite_checkbox)
        layout.addWidget(self.headless_checkbox)

        self.left_layout.addWidget(self.options_label)
        self.left_layout.addLayout(layout)
        self.left_layout.addSpacing(20)

    def init_ui_progress_table(self):
        self.output_table = QTableWidget(0, len(self.TABLE_HEADERS))
        self.output_table.setHorizontalHeaderLabels(self.TABLE_HEADERS)
        self.output_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.output_table.setSelectionMode(QTableWidget.NoSelection)
        self.output_table.setFocusPolicy(Qt.NoFocus)

        header = self.output_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        for i in range(1, len(self.TABLE_HEADERS)):
            header.setSectionResizeMode(i, QHeaderView.ResizeToContents)

        self.left_layout.addWidget(self.output_table)

    def init_ui_execution_controls(self):
        # Create a QLabel to display the GIF
        self.gif_label = QLabel()
        self.gif_label.setFixedSize(32, 32)
        self.gif_label.setAlignment(Qt.AlignCenter)

        # Load the GIF into QMovie
        self.gif_status = QMovie(Animations.COMPLETED)
        self.gif_status.setScaledSize(QSize(32, 32))
        self.gif_status.setCacheMode(QMovie.CacheAll)
        self.gif_status.finished.connect(self.on_gif_finished)
        self.gif_label.setMovie(self.gif_status)

        self.running_label = QLabel("")
        self.running_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.running_label.setStyleSheet("padding-left: 20px;padding-right: 20px;")

        self.execute_button = QPushButton("Run")
        self.execute_button.setEnabled(False)
        self.execute_button.clicked.connect(self.on_button_execute)

        self.left_layout.addWidget(self.execute_button)


    def init_ui_status_bar(self):
        """Create and configure the status bar."""

        # --- Create and attach the status bar ---
        self.status_bar = QStatusBar(self)
        self.setStatusBar(self.status_bar)

        self.status_bar.addWidget(self.gif_label)
        self.status_bar.addWidget(self.running_label)

        # --- Theme switch (right side / permanent widget) ---
        self.theme_switch = QCheckBox("Dark mode")
        self.theme_switch.setChecked(False)
        self.theme_switch.stateChanged.connect(self.on_theme_switch_changed)
        self.status_bar.addPermanentWidget(self.theme_switch)

    def on_theme_switch_changed(self, state: int):
        is_dark = state == Qt.Checked

        if is_dark:
            # Apply dark theme here
            self.set_theme(Themes.DARK)
        else:
            # Apply light theme here
            self.set_theme(Themes.LIGHT)

    def init_finish(self):
        self.set_theme(RunningConfig.theme)
        self.set_running_state(RunStates.INIT)

        self.update_target_buttons()

    def on_button_execute(self):
        self.execute_button.setEnabled(False)

        self.thread_execution = threading.Thread(target=self.execute)
        self.thread_execution.start()

    def on_gif_finished(self):
        log.debug(f"GIF finished: {self.run_state}")
        if self.run_state == RunStates.FINISHED:
            log.debug("GIF stopped")
            self.gif_status.stop()

    # ------------------------------------------------------------------
    # Source selection
    # ------------------------------------------------------------------

    def select_source_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Select Source File(s)",
            directory=package_path,
            filter=FileTypeConfig.dialog_filter(*self.INPUT_FILE_TYPES),
            options=QFileDialog.DontUseNativeDialog
        )
        if not files:
            return

        self.source_type = "file" if len(files) == 1 else "files"
        self.source_files = sorted(files)
        self.source_entry.setText(", ".join(self.source_files))

        self.after_source_selected()

    def select_source_folder(self):
        folder = QFileDialog.getExistingDirectory(self,
                                                  "Select Source Folder",
                                                  directory=package_path,
                                                  options=QFileDialog.DontUseNativeDialog)
        if not folder:
            log.warning("Folder is not valid. Terminating.")
            return

        log.debug(f"Selected folder: {folder}")
        log.debug(f"Found {len(os.listdir(folder))} files.")

        self.source_type = "folder"
        self.source_entry.setText(folder)

        source_files = list()
        valid_input_extensions = [ext for f_type in self.INPUT_FILE_TYPES for ext in f_type.extensions]
        for file_i in os.listdir(folder):
            if Path(file_i).suffix.lower() in valid_input_extensions:
                source_files.append(os.path.join(folder, file_i))
        self.source_files = sorted(source_files)

        log.debug(f"Identified {len(self.source_files)} relevant files.")

        self.after_source_selected()

    def after_source_selected(self):
        self.populate_table(self.source_files)
        self.target_entry.clear()
        if self.source_type == "file":
            self.target_location = str(Path(self.source_files[0]).with_suffix(self.OUTPUT_FILE_TYPES[0].extensions[0]))
            self.target_entry.setText(self.target_location)
        self.update_target_buttons()
        self.update_execute_button()
        self.set_running_state(RunStates.INIT)
        self.update_table()


    # ------------------------------------------------------------------
    # Target selection
    # ------------------------------------------------------------------

    def select_target_file(self):
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Select Target File",
            directory=package_path,
            filter=FileTypeConfig.dialog_filter(*self.OUTPUT_FILE_TYPES),
            options=QFileDialog.DontUseNativeDialog
        )
        if path:
            self.target_location = path
            self.target_entry.setText(path)
            self.update_execute_button()
            self.set_running_state(RunStates.INIT)

    def select_target_folder(self):
        folder = QFileDialog.getExistingDirectory(self,
                                                  "Select Target Folder",
                                                  directory=package_path,
                                                  options=QFileDialog.DontUseNativeDialog)
        if folder:
            self.target_location = folder
            self.target_entry.setText(folder)
            self.update_execute_button()
            self.set_running_state(RunStates.INIT)

    def update_target_buttons(self):
        self.browse_target_file_btn.setEnabled(self.source_type == "file")
        self.browse_target_folder_btn.setEnabled(self.source_type in ("files", "folder"))

    # ------------------------------------------------------------------
    # Progress table
    # ------------------------------------------------------------------

    def populate_table(self, files):
        self.output_table.setRowCount(0)
        self.file_row_map.clear()
        self.row_colors = list()

        for row, path in enumerate(files):
            self.output_table.insertRow(row)
            self.file_row_map[path] = row

            self.output_table.setItem(row, 0, QTableWidgetItem(os.path.basename(path)))
            for col in range(1, len(self.TABLE_HEADERS) - 1):
                item = QTableWidgetItem("0")
                item.setTextAlignment(Qt.AlignCenter)
                self.output_table.setItem(row, col, item)

            checkbox = QCheckBox()
            checkbox.setEnabled(False)
            container = QWidget()
            layout = QHBoxLayout(container)
            layout.addWidget(checkbox)
            layout.setAlignment(Qt.AlignCenter)
            layout.setContentsMargins(0, 0, 0, 0)
            self.output_table.setCellWidget(row, len(self.TABLE_HEADERS) - 1, container)

            self.row_colors.append(ColorRole.INIT)

    def update_table(self):
        pass

    def set_processing_result(self, file_path, successful_rows, skipped_rows):
        if file_path not in self.file_row_map:
            return

        row = self.file_row_map[file_path]

        self.output_table.item(row, 2).setText(str(successful_rows))
        self.output_table.item(row, 3).setText(str(skipped_rows))

        relevant = int(self.output_table.item(row, 1).text())
        total_processed = successful_rows + skipped_rows

        finished = total_processed == relevant

        checkbox = self.output_table.cellWidget(row, 4).findChild(QCheckBox)
        checkbox.setChecked(finished)

        if finished:
            if skipped_rows > 0:
                color = Colors.TableBackground[RunningConfig.theme][ColorRole.SKIPPED]
                self.row_colors[row] = ColorRole.SKIPPED
            else:
                color = Colors.TableBackground[RunningConfig.theme][ColorRole.SUCCESS]
                self.row_colors[row] = ColorRole.SUCCESS
        elif total_processed > 0:
            color = Colors.TableBackground[RunningConfig.theme][ColorRole.ACTIVE]
            self.row_colors[row] = ColorRole.ACTIVE
        else:
            return

        for col in range(self.output_table.columnCount()):
            item = self.output_table.item(row, col)
            if item:
                item.setBackground(QColor(color))

        QApplication.processEvents()

    def update_table_colors(self):
        if self.row_colors is None:
            return

        for row, role in enumerate(self.row_colors):
            if role == ColorRole.INIT:
                # skip if color has not been changed
                continue

            color = QColor(Colors.TableBackground[RunningConfig.theme][role])

            for col in range(self.output_table.columnCount()):
                item = self.output_table.item(row, col)
                if item is not None:
                    item.setBackground(color)

    # ------------------------------------------------------------------
    # Running indicator
    # ------------------------------------------------------------------

    def _animate_running(self):
        if self.run_state != RunStates.RUNNING:
            return
        dots = "." * ((self.running_timer.remainingTime() // 500) % 4)
        self.running_label.setText(f"Running{dots}")

    def set_running_state(self, run_state: str):
        """Start or stop the running indicator animation."""
        if run_state == RunStates.RUNNING:
            log.debug("Setting run state to: Running")
            self.running_label.setText(f"Running...")
            self.set_status_animation(Animations.GEOLOCATION)
        elif run_state == RunStates.FINISHED:
            log.debug("Setting run state to: Finished")
            self.running_label.setText(f"Scraping completed.")
            self.set_status_animation(Animations.COMPLETED)
            self.execute_button.setEnabled(True)
        elif run_state == RunStates.INIT:
            log.debug("Setting run state to: Init")
            if self.source_entry.text() == "":
                status_text = "Please select source file(s)/folder."
            elif self.target_entry.text() == "":
                status_text = "Please select a target file/folder."
            else:
                status_text = "GeoPro ready!"
            self.running_label.setText(status_text)
            self.set_status_animation(Animations.GEOLOCATION, AnimationStates.FRAME)
        elif run_state == RunStates.USER_INPUT:
            self.running_label.setText("Waiting for user input...")
            self.set_status_animation(Animations.MATCHING)
        elif run_state == RunStates.STOPPED:
            self.running_label.setText("Exiting application...")

        QApplication.processEvents()

        self.run_state = run_state

    def set_status_animation(self, animation=None, animation_state=AnimationStates.PLAYING):
        # if animation_state in [AnimationStates.PLAYING, AnimationStates.STOPPED]:
        self.gif_status.stop()

        if animation is None:
            # reset current animation if no new animation is provided, current theme is automatically used
            self.gif_status.setFileName(Animations.get_path(RunningConfig.animation))
        else:
            # set to new animation with current theme
            self.gif_status.setFileName(Animations.get_path(animation))
            RunningConfig.animation = animation

        if animation_state == AnimationStates.PLAYING:
            self.gif_status.start()

        if animation_state == AnimationStates.FRAME:
            self.gif_status.jumpToFrame(self.gif_status.frameCount()-1)

        RunningConfig.animation_state = animation_state

        log.debug(f"Set status animation to: {RunningConfig.animation}")
        log.debug(f"Set animation state to: {RunningConfig.animation_state}")

    def set_theme(self, theme):
        RunningConfig.theme = theme

        # update UI button - only necessary during initialization
        self.theme_switch.setChecked(theme == Themes.DARK)

        # update global theme
        qdarktheme.setup_theme(theme)

        # update table row color
        self.update_table_colors()

        # update current GIF
        # self.set_status_animation(animation_state=AnimationStates.PLAYING)
        self.set_status_animation(animation_state=RunningConfig.animation_state)

    def update_execute_button(self):
        self.execute_button.setEnabled(
            bool(self.source_files) and bool(self.target_location)
        )

    # ------------------------------------------------------------------
    # Hooks
    # ------------------------------------------------------------------

    def execute(self):
        """Must be implemented by subclass"""
        raise NotImplementedError

    def closeEvent(self, event):
        # Called when the user closes the window

        log.info("Waiting for worker thread to stop...")
        if self.thread_execution is not None:
            self.thread_execution.join()
        log.info("Worker thread stopped. Exiting program now.")
        event.accept()  # accept the close