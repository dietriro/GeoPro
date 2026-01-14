import sys
import os
import json
import logging
from PyQt5.QtWidgets import QApplication, QLabel, QLineEdit, QComboBox,QHBoxLayout


from geopro.functions.osm_fitting import process_places_to_kml
from geopro.apps.base import BaseGeoProApp
from geopro.core import FileTypeConfig

log = logging.getLogger("geopro")
log.setLevel(logging.DEBUG)


class RunStates:
    INIT = "initialized"
    RUNNING = "running"
    FINISHED = "finished"


class GMapsGeoProApp(BaseGeoProApp):
    WINDOW_TITLE = "GeoPro - OSM-Place-Matcher"
    INPUT_FILE_TYPES = [FileTypeConfig.GEOJSON, FileTypeConfig.JSON]
    OUTPUT_FILE_TYPES = [FileTypeConfig.KML]

    def __init__(self):
        super().__init__()

        self.init_ui_source_selection()
        self.init_ui_target_selection()

        self.init_ui_options()

        self.init_ui_progress_table()

        self.init_ui_execution_controls()

        self.init_finish()

    def init_finish(self):
        self.headless_checkbox.setEnabled(False)
        super().init_finish()


    # ------------------------------------------------------------------
    # CSV relevance counting
    # ------------------------------------------------------------------
    def update_table(self):
        # 1. update number of relevant rows
        for path in self.source_files:
            relevant = self.count_relevant_places(path)
            self.output_table.item(self.file_row_map[path], 1).setText(str(relevant))

    def count_relevant_places(self, file_path):
        """Count non-empty rows where URL column contains Google Maps."""

        """
        Return the number of features in a GeoJSON FeatureCollection.

        :param file_path: Path to a .geojson file
        :return: Number of features, or 0 if invalid
        """
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            if data.get("type") != "FeatureCollection":
                log.warning(f"File {file_path} does not contain a FeatureCollection.")
                return 0

            features = data.get("features")
            if not isinstance(features, list):
                log.warning(f"File {file_path} does not contain a list of Features.")
                return 0

            return len(features)

        except (OSError, json.JSONDecodeError) as e:
            log.error(f"Error decoding file {file_path}: {e}")
            return 0

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------
    def execute(self):
        self.set_running_state(RunStates.RUNNING)

        # Runs scraping for each file
        for input_file_path in self.source_files:
            if os.path.isdir(self.target_location):
                target_file_name = f"{os.path.splitext(os.path.basename(input_file_path))[0]}.kml"
                output_file_path = os.path.join(self.target_location, target_file_name)
            else:
                output_file_path = self.target_location
            process_places_to_kml(input_file_path=input_file_path,
                             output_file_path=output_file_path,
                             overwrite_output=self.overwrite_target,
                             update_function=self.set_processing_result)

        self.set_running_state(RunStates.FINISHED)



if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = GMapsGeoProApp()
    window.show()
    sys.exit(app.exec_())
