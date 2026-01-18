import sys
import os
import csv
import logging
from PyQt5.QtWidgets import QApplication, QLabel, QLineEdit, QComboBox,QHBoxLayout


from geopro.functions.gmaps_scraping import scrape_from_file, SupportedMethods
from geopro.apps.base import BaseGeoProApp
from geopro.core import FileTypeConfig, EmitterGMaps

log = logging.getLogger("geopro")


class RunStates:
    INIT = "initialized"
    RUNNING = "running"
    FINISHED = "finished"


class GMapsGeoProApp(BaseGeoProApp):
    WINDOW_TITLE = "GeoPro - GMaps-Scraper"
    INPUT_FILE_TYPES = [FileTypeConfig.CSV]
    OUTPUT_FILE_TYPES = [FileTypeConfig.JSON, FileTypeConfig.GEOJSON]

    def __init__(self):
        super().__init__()

        self.init_ui_source_selection()
        self.init_ui_target_selection()

        self.init_ui_method_selection()
        self.init_ui_api_key()

        self.init_ui_options()

        self.init_ui_progress_table()

        self.init_ui_execution_controls()

        self.init_ui_status_bar()

        self.emitter = EmitterGMaps()
        self.emitter.status.connect(self.set_running_state)
        self.emitter.set_processing_result.connect(self.set_processing_result)

        self.init_finish()

    # -------------------------
    # Initialization
    # -------------------------
    def init_finish(self):
        super().init_finish()

        # disable splitter as the right side is currently not needed
        self.splitter.widget(1).hide()
        self.splitter.handle(1).setEnabled(False)
        self.splitter.setSizes([1, 0])

    def init_ui_method_selection(self):
        method_layout = QHBoxLayout()
        # Label
        self.method_label = QLabel("Select scraping method:")
        method_layout.addWidget(self.method_label)

        # Dropdown
        self.method_dropdown = QComboBox()
        self.method_dropdown.addItems(["Selenium", "GMaps Api"])
        method_layout.addWidget(self.method_dropdown)
        self.left_layout.addLayout(method_layout)

        # Variable holding the current selection
        self.scraping_method = self.method_dropdown.currentText()

        # Connect change signal
        self.method_dropdown.currentTextChanged.connect(self.on_method_changed)

    def init_ui_api_key(self):
        api_layout = QHBoxLayout()

        self.api_label = QLabel("Api key:")
        api_layout.addWidget(self.api_label)

        self.api_entry = QLineEdit()
        self.api_entry.setEnabled(False)
        api_layout.addWidget(self.api_entry)

        self.left_layout.addLayout(api_layout)

        self.left_layout.addSpacing(20)


    # -------------------------
    # Events
    # -------------------------
    def on_method_changed(self, method):
        self.scraping_method = method.lower().replace(" ", "_")
        self.api_entry.setEnabled(self.scraping_method == SupportedMethods.GMAPS_API)
        log.debug(f"Scraping method changed: {self.scraping_method}")


    # ------------------------------------------------------------------
    # CSV relevance counting
    # ------------------------------------------------------------------
    def update_table(self):
        # 1. update number of relevant rows
        for path in self.source_files:
            relevant = self.count_relevant_places(path)
            self.output_table.item(self.file_row_map[path], 1).setText(str(relevant))

    def count_relevant_places(self, csv_path):
        """Count non-empty rows where URL column contains Google Maps."""
        try:
            with open(csv_path, newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                if "URL" not in reader.fieldnames:
                    return 0

                count = 0
                for row in reader:
                    url = (row.get("URL") or "").strip()
                    if url and "www.google.com/maps" in url:
                        count += 1
                return count
        except Exception:
            return 0


    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------
    def execute(self):
        self.emitter.status.emit(RunStates.RUNNING)

        # Runs scraping for each file
        for input_file_path in self.source_files:
            if os.path.isdir(self.target_location):
                target_file_name = f"{os.path.splitext(os.path.basename(input_file_path))[0]}.geojson"
                output_file_path = os.path.join(self.target_location, target_file_name)
            else:
                output_file_path = self.target_location
            scrape_from_file(input_file=input_file_path,
                             output_file=output_file_path,
                             overwrite_output=self.overwrite_target,
                             update_function=self.emitter.set_processing_result.emit,
                             run_headless=self.run_headless,
                             scraping_method=self.scraping_method,
                             api_key=self.api_entry.text())

        self.emitter.status.emit(RunStates.FINISHED)



if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = GMapsGeoProApp()
    window.show()
    sys.exit(app.exec_())
