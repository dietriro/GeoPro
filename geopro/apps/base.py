import os
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QPushButton, QLineEdit,
    QFileDialog, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QCheckBox, QHeaderView, QApplication
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QColor

from geopro.core import FileTypeConfig, RunStates
from geopro.logging import setup_logging

log = setup_logging()


class BaseGeoProApp(QWidget):
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

        self.layout = QVBoxLayout()
        self._init_window()






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

        self.layout.addWidget(self.source_label)
        self.layout.addLayout(btns)
        self.layout.addWidget(self.source_entry)
        self.layout.addSpacing(20)

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

        self.layout.addWidget(self.target_label)
        self.layout.addLayout(btns)
        self.layout.addWidget(self.target_entry)

        self.layout.addSpacing(20)

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

        self.layout.addWidget(self.options_label)
        self.layout.addLayout(layout)
        self.layout.addSpacing(20)

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

        self.layout.addWidget(self.output_table)

    def init_ui_execution_controls(self):
        self.running_label = QLabel("")
        self.running_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        self.execute_button = QPushButton("Run")
        self.execute_button.setEnabled(False)
        self.execute_button.clicked.connect(self.execute)
        # self.execute_button.setFixedWidth(250)

        self.running_timer = QTimer()
        self.running_timer.setInterval(500)
        self.running_timer.timeout.connect(self._animate_running)

        bottom = QHBoxLayout()
        bottom.addWidget(self.running_label)
        bottom.addStretch()
        bottom.addWidget(self.execute_button)

        self.layout.addLayout(bottom)

    def init_finish(self):
        self.set_running_state(RunStates.INIT)
        self.update_target_buttons()

        self.setLayout(self.layout)

    # ------------------------------------------------------------------
    # Source selection
    # ------------------------------------------------------------------

    def select_source_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Select Files",
            "",
            FileTypeConfig.dialog_filter(*self.INPUT_FILE_TYPES)
        )
        if not files:
            return

        self.source_type = "file" if len(files) == 1 else "files"
        self.source_files = sorted(files)
        self.source_entry.setText(", ".join(files))

        self.populate_table(self.source_files)
        self.after_source_selected()

    def select_source_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Folder")
        if not folder:
            return

        self.source_type = "folder"
        self.source_entry.setText(folder)

        self.source_files = sorted(
            os.path.join(folder, f)
            for f in os.listdir(folder)
            if any(f.lower().endswith(ext) for ext in self.INPUT_FILE_TYPES[0].extensions)
        )

        self.populate_table(self.source_files)
        self.after_source_selected()

    def after_source_selected(self):
        self.target_entry.clear()
        self.update_target_buttons()
        self.update_execute_button()
        self.set_running_state(RunStates.INIT)

    # ------------------------------------------------------------------
    # Target selection
    # ------------------------------------------------------------------

    def select_target_file(self):
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Select Target File",
            "",
            FileTypeConfig.dialog_filter(*self.OUTPUT_FILE_TYPES)
        )
        if path:
            self.target_location = path
            self.target_entry.setText(path)
            self.update_execute_button()
            self.set_running_state(RunStates.INIT)

    def select_target_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Target Folder")
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

    def set_processing_result(self, file_path, successful_rows, skipped_rows, finished=None
    ):
        if file_path not in self.file_row_map:
            return

        row = self.file_row_map[file_path]

        self.output_table.item(row, 2).setText(str(successful_rows))
        self.output_table.item(row, 3).setText(str(skipped_rows))

        relevant = int(self.output_table.item(row, 1).text())
        total_processed = successful_rows + skipped_rows

        if finished is None:
            finished = total_processed == relevant

        checkbox = self.output_table.cellWidget(row, 4).findChild(QCheckBox)
        checkbox.setChecked(finished)

        if finished:
            color = QColor("#FFF59D") if skipped_rows > 0 else QColor("#C8E6C9")
        elif total_processed > 0:
            color = QColor("#BBDEFB")
        else:
            return

        for col in range(self.output_table.columnCount()):
            item = self.output_table.item(row, col)
            if item:
                item.setBackground(color)

        QApplication.processEvents()

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
            self.running_timer.start()
        elif run_state == RunStates.FINISHED:
            log.debug("Setting run state to: Finished")
            self.running_label.setText(f"Scraping completed.")
            self.running_timer.stop()
        elif run_state == RunStates.INIT:
            log.debug("Setting run state to: Init")
            if self.source_entry.text() == "":
                status_text = "Please select source file(s)/folder."
            elif self.target_entry.text() == "":
                status_text = "Please select a target file/folder."
            else:
                status_text = "Ready to scrape data from Google Maps."
            self.running_label.setText(status_text)
            self.running_timer.stop()
        self.run_state = run_state

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