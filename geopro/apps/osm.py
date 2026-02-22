import sys
import os
import json
import logging

from PyQt5.QtCore import Qt, QEventLoop, QObject, pyqtSignal, pyqtSlot, QPoint, QSize
from PyQt5.QtGui import QPixmap, QPainter, QPolygon, QColor, QFont, QIcon
from PyQt5.QtWebChannel import QWebChannel
from PyQt5.QtWebEngineWidgets import QWebEngineView
from PyQt5.QtWidgets import QApplication, QLabel, QLineEdit, QComboBox, QHBoxLayout, QWidget, QVBoxLayout, QTableWidget, \
    QTableWidgetItem, QPushButton, QMessageBox, QHeaderView, QTreeWidgetItem, QTreeWidget

from geopro.functions.osm_fitting import MatchingMethods, OSMMatcher
from geopro.apps.base import BaseGeoProApp
from geopro.core import FileTypeConfig, RunStates, EmitterOSM
from geopro.config import Icons, RANGES, Commands
from geopro.ui.widgets import IconTextButton

log = logging.getLogger("geopro")
log.setLevel(logging.DEBUG)

DEFAULT_THRESHOLD = 0.7


class MapBridge(QObject):
    markerClicked = pyqtSignal(int)

    @pyqtSlot(int)
    def on_marker_clicked(self, index):
        self.markerClicked.emit(index)


class OSMDataViewer(QWidget):
    def __init__(self, data: dict, parent=None):
        super().__init__(parent)

        self.setWindowTitle("OSM Element Viewer")
        self.resize(600, 400)

        layout = QVBoxLayout(self)

        self.tree = QTreeWidget()
        self.tree.setColumnCount(2)
        self.tree.setHeaderLabels(["Key", "Value"])
        # self.tree.header().setStretchLastSection(True)
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.tree.header().setSectionResizeMode(1, QHeaderView.Stretch)

        layout.addWidget(self.tree)

        self.populate_tree(data)
        self.tree.expandToDepth(0)  # expand first level

    def populate_tree(self, data):
        self.tree.clear()
        root = self.tree.invisibleRootItem()

        # If root is a list with a single element → unwrap it
        if isinstance(data, list) and len(data) == 1:
            self._add_items(root, data[0])
        else:
            self._add_items(root, data)

    def _add_items(self, parent_item, value):
        """
        Recursively populate a QTreeWidgetItem from a dict or list.
        Simple values are shown in column 2 of the same row.
        """

        # If the root itself is a dict
        if isinstance(value, dict):
            for key, val in value.items():
                item = QTreeWidgetItem(parent_item)
                item.setText(0, str(key))

                if isinstance(val, (dict, list)):
                    # Complex type → recurse
                    self._add_items(item, val)
                else:
                    # Simple value → display in column 2
                    item.setText(1, str(val))

        # If the root itself is a list
        elif isinstance(value, list):
            for index, val in enumerate(value):
                item = QTreeWidgetItem(parent_item)
                item.setText(0, f"[{index}]")

                if isinstance(val, (dict, list)):
                    self._add_items(item, val)
                else:
                    item.setText(1, str(val))

        # If the root itself is a simple value
        else:
            parent_item.setText(1, str(value))


class OSMGeoProApp(BaseGeoProApp):
    WINDOW_TITLE = "GeoPro - OSM-Place-Matcher"
    WINDOW_GEOMETRY = (1150, 850)
    INPUT_FILE_TYPES = [FileTypeConfig.GEOJSON, FileTypeConfig.JSON]
    OUTPUT_FILE_TYPES = [FileTypeConfig.KML]

    def __init__(self):
        super().__init__()
        self.emitter = EmitterOSM()
        self.emitter.status.connect(self.set_running_state)
        self.emitter.user_match_selection.connect(self.user_match_selection)
        self.emitter.set_processing_result.connect(self.set_processing_result)
        self.emitter.reset_matching.connect(self.reset_matching)

        self.osm_matcher = OSMMatcher(update_function=self.emitter.set_processing_result.emit,
                                      user_match_selection=self.trigger_user_match_selection)

        self.match_selection_loop = None
        self.selected_match = None
        self.matches_data = None
        self.extended_match_data_viewer = None

        self.init_ui_source_selection()
        self.init_ui_target_selection()

        self.init_ui_options()
        self.init_ui_matching_method()
        self.init_ui_threshold()

        self.init_ui_progress_table()

        self.init_ui_execution_controls()
        self.init_ui_status_bar()

        self.init_ui_map_matching()
        self.init_ui_original_location_simple()
        self.init_ui_matching_table()
        self.init_ui_matching_selection()

        self.init_finish()

    def init_ui_matching_method(self):
        method_layout = QHBoxLayout()
        # Label
        self.method_label = QLabel("Select matching method:")
        method_layout.addWidget(self.method_label)

        # Dropdown
        self.method_dropdown = QComboBox()
        self.method_dropdown.addItems([m.capitalize() for m in [MatchingMethods.BEST,
                                                                MatchingMethods.ALL,
                                                                MatchingMethods.THRESHOLD]])
        method_layout.addWidget(self.method_dropdown)
        self.left_layout.addLayout(method_layout)

        # Variable holding the current selection
        self.matching_method = self.method_dropdown.currentText().lower()

        # Connect change signal
        self.method_dropdown.currentTextChanged.connect(self.on_method_changed)

    def init_ui_threshold(self):
        threshold_layout = QHBoxLayout()

        self.threshold_label = QLabel("Threshold (0.0 - 1.0):")
        threshold_layout.addWidget(self.threshold_label)

        self.threshold_entry = QLineEdit()
        self.threshold_entry.setText(str(DEFAULT_THRESHOLD))
        self.threshold_entry.setEnabled(False)
        threshold_layout.addWidget(self.threshold_entry)

        self.left_layout.addLayout(threshold_layout)

        self.left_layout.addSpacing(20)

    def init_ui_map_matching(self):
        self.map_container = QWidget()
        self.map_layout = QVBoxLayout(self.map_container)

        self.right_layout.addWidget(self.map_container, stretch=4)

        self.map_view = QWebEngineView()
        self.map_view.page().setBackgroundColor(Qt.black)
        self.map_layout.addWidget(self.map_view)

        self.bridge = MapBridge()
        self.bridge.markerClicked.connect(self.on_click_map)

        channel = QWebChannel(self.map_view.page())
        channel.registerObject("bridge", self.bridge)
        self.map_view.page().setWebChannel(channel)

    def init_ui_original_location(self):
        self.layout_match_original = QVBoxLayout()
        self.layout_match_original.setContentsMargins(10, 0, 10, 0)
        self.layout_match_original.setSpacing(0)
        self.right_layout.addLayout(self.layout_match_original)

        self.layout_match_title = QHBoxLayout()
        self.layout_match_coordinates = QHBoxLayout()
        self.layout_match_title.setSpacing(0)
        self.layout_match_coordinates.setSpacing(0)
        self.layout_match_original.addLayout(self.layout_match_title)
        self.layout_match_original.addLayout(self.layout_match_coordinates)

        self.label_matching_title = QLabel("Match original location:")
        self.label_matching_name = QLabel("")
        self.label_matching_lat = QLabel("")
        self.label_matching_lon = QLabel("")

        self.label_matching_title.setStyleSheet("background-color: #FFFFFF;padding-left: 00px;padding-right: 20px;")
        self.label_matching_name.setStyleSheet("background-color: #FFFFFF;padding-left: 0px;padding-right: 20px;")
        self.label_matching_lat.setStyleSheet("background-color: #FFFFFF;padding-left: 0px;padding-right: 20px;")
        self.label_matching_lon.setStyleSheet("background-color: #FFFFFF;padding-left: 0px;padding-right: 20px;")

        self.layout_match_title.addWidget(self.label_matching_title)
        self.layout_match_title.addWidget(self.label_matching_lat)
        self.layout_match_coordinates.addWidget(self.label_matching_name)
        self.layout_match_coordinates.addWidget(self.label_matching_lon)

        # self.right_layout.setContentsMargins(30, 30, 30, 30)
        # self.right_layout.setSpacing(60)

    def init_ui_original_location_simple(self):
        self.layout_match_original = QHBoxLayout()
        self.layout_match_original.setContentsMargins(10, 0, 10, 0)
        self.layout_match_original.setSpacing(0)
        self.right_layout.addLayout(self.layout_match_original)

        # self.icon_match_original = QIcon(Icons.MARKER_MATCH)
        self.label_matching_name = QLabel("")
        self.label_matching_name.setTextInteractionFlags(Qt.TextSelectableByMouse)

        self.button_trigger_original = QPushButton()
        self.button_trigger_original.setIcon(QIcon(Icons.MARKER_ORIGINAL))  # set the icon
        self.button_trigger_original.setIconSize(QSize(18, 18))  # control size
        self.button_trigger_original.setFixedSize(24, 24)  # button size matches icon nicely
        self.button_trigger_original.clicked.connect(self.on_button_org_trigger)

        self.button_decrease_range = QPushButton("+")
        self.button_decrease_range.setFixedSize(24, 24)  # button size matches icon nicely
        self.button_decrease_range.clicked.connect(lambda: self.on_button_range(Commands.ZOOM_IN))

        self.label_range = QLabel("")
        self.label_range.setFixedSize(72, 24)
        self.label_range.setAlignment(Qt.AlignCenter)
        self.label_range.setTextInteractionFlags(Qt.TextSelectableByMouse)

        self.button_increase_range = QPushButton("-")
        self.button_increase_range.setFixedSize(24, 24)  # button size matches icon nicely
        self.button_increase_range.clicked.connect(lambda: self.on_button_range(Commands.ZOOM_OUT))

        self.label_matching_name.setStyleSheet("padding-left: 5px;padding-right: 20px;")
        # self.label_matching_name.setStyleSheet("background-color: #FFFFFF;padding-left: 5px;padding-right: 20px;")

        self.layout_match_original.addWidget(self.button_trigger_original)
        self.layout_match_original.addWidget(self.label_matching_name)
        self.layout_match_original.addWidget(self.button_increase_range)
        self.layout_match_original.addWidget(self.label_range)
        self.layout_match_original.addWidget(self.button_decrease_range)

    def init_ui_matching_table(self):
        self.matches_container = QWidget()
        self.matches_layout = QVBoxLayout(self.matches_container)

        self.right_layout.addWidget(self.matches_container, stretch=4)

        self.matches_table = QTableWidget()
        self.matches_table.setColumnCount(3)
        self.matches_table.setHorizontalHeaderLabels([
            "Name",
            # "Latitude",
            # "Longitude",
            # "Distance score",
            # "Name score",
            "Distance (m)",
            "Total score",
        ])
        self.matches_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.matches_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.matches_table.setSelectionMode(QTableWidget.SingleSelection)
        self.matches_table.itemSelectionChanged.connect(self.on_click_table)
        self.matches_table.itemDoubleClicked.connect(self.on_double_click_table)

        header = self.matches_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        for i in range(1, self.matches_table.columnCount()):
            header.setSectionResizeMode(i, QHeaderView.ResizeToContents)

        self.matches_layout.addWidget(self.matches_table)

    def init_ui_matching_selection(self):
        self.matches_selection_layout = QHBoxLayout()
        self.matches_selection_layout.setContentsMargins(10, 0, 10, 0)

        self.right_layout.addLayout(self.matches_selection_layout, stretch=1)

        self.matches_select_button = IconTextButton(QIcon(Icons.MARKER_MATCH), "Confirm selection")
        self.matches_select_button.clicked.connect(self.on_button_select_match)

        self.org_loc_select_button = IconTextButton(QIcon(Icons.MARKER_ORIGINAL), "Confirm original location")
        self.org_loc_select_button.clicked.connect(self.on_button_select_org_loc)


        self.matches_selection_layout.addWidget(self.org_loc_select_button)
        self.matches_selection_layout.addWidget(self.matches_select_button)

    def init_finish(self):
        self.headless_checkbox.setEnabled(False)
        self.reset_matching()
        super().init_finish()

    # ------------------------------------------------------------------
    # Event functions
    # ------------------------------------------------------------------
    def on_method_changed(self, method):
        self.matching_method = method.lower()
        self.threshold_entry.setEnabled(self.matching_method == MatchingMethods.THRESHOLD)
        log.debug(f"Matching method changed: {self.matching_method}")

    def on_button_select_org_loc(self):
        self.selected_match = -1

        if self.match_selection_loop is not None:
            self.match_selection_loop.quit()
            self.match_selection_loop = None

    def on_button_select_match(self):
        if self.selected_match is None:
            QMessageBox.warning(self, "No selection", "Please select a place.")
            return

        if self.match_selection_loop is not None:
            self.match_selection_loop.quit()
            self.match_selection_loop = None

    def on_button_org_trigger(self):
        """
        Show original location on map when the user triggers it
        """
        self.map_view.page().runJavaScript(
            f"originalMarker.openPopup();"
        )

        log.debug(f"User triggered original marker")

    def on_button_range(self, direction):
        self.selected_match = direction

        if self.match_selection_loop is not None:
            self.match_selection_loop.quit()
            self.match_selection_loop = None

    def on_click_table(self):
        """
        Update selected_match when the user selects a row in the matches table.
        """
        selected_rows = self.matches_table.selectionModel().selectedRows()

        if not selected_rows:
            self.selected_match = None
            return

        # SingleSelection → take first
        row_index = selected_rows[0].row()
        self.selected_match = row_index

        self.map_view.page().runJavaScript(
            f"marker_{row_index + 1}.openPopup();"
        )

        if self.extended_match_data_viewer is not None:
            self.extended_match_data_viewer.populate_tree(self.matches_data[self.selected_match])

        log.debug(f"User selected match row: {row_index}")

    def on_double_click_table(self):
        """
                Update selected_match when the user selects a row in the matches table.
                """
        self.on_click_table()

        if self.extended_match_data_viewer is None:
            self.extended_match_data_viewer = OSMDataViewer(self.matches_data[self.selected_match])

        self.extended_match_data_viewer.show()

        # self.extended_match_data_viewer = OSMDataViewer(self.matches_data)
        # self.extended_match_data_viewer.show()

    def on_click_map(self, selected_index):
        self.matches_table.blockSignals(True)
        self.matches_table.selectRow(selected_index)
        self.matches_table.blockSignals(False)
        self.selected_match = selected_index

        log.debug(f"User selected match row: {self.selected_match}")

    def user_match_selection(self, name_org, lat_org, lon_org, matches, range):
        # update animation
        self.set_running_state(RunStates.USER_INPUT)

        # update map
        self.load_map(lat_org, lon_org, matches)

        # update original location
        self.set_matching_original_loc(name_org, lat_org, lon_org)

        # update table
        self.update_matches_table(matches)

        # update list of matches data from OSM
        self.matches_data = matches

        # update range label
        self.label_range.setText(str(range))

        # reset selected match and enable button
        self.selected_match = None
        self.matches_select_button.setEnabled(True)
        self.org_loc_select_button.setEnabled(True)
        self.button_trigger_original.setEnabled(True)
        if RANGES.index(range) > 0:
            self.button_decrease_range.setEnabled(True)
        if RANGES.index(range) < len(RANGES) - 1:
            self.button_increase_range.setEnabled(True)

    def trigger_user_match_selection(self, name_org, lat_org, lon_org, matches, range):
        if self.osm_matcher.stop_requested:
            return Commands.EXIT

        self.emitter.user_match_selection.emit(name_org, lat_org, lon_org, matches, range)

        # block function until selection is made
        self.match_selection_loop = QEventLoop()
        self.match_selection_loop.exec_()

        # store the selected match picked by the user because it gets overwritten by the next commands
        selected_match = self.selected_match

        # reset matching ui
        # self.emitter.reset_matching.emit()

        # set run state to running
        self.emitter.status.emit(RunStates.RUNNING)

        return selected_match

    def set_running_state(self, run_state: str):
        super().set_running_state(run_state)

        if run_state == RunStates.RUNNING:
            self.reset_matching()

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
    # Map matching
    # ------------------------------------------------------------------

    # def _leaflet_markers_js(self, matches):
    #     js = []
    #
    #     for m in matches:
    #         popup_html = f"{m.get('name', '')}<br>Score: {m.get('final_score', 0)}"
    #
    #         js.append(
    #             f"""
    #             L.marker([{m['lat']}, {m['lon']}])
    #               .addTo(map)
    #               .bindPopup({json.dumps(popup_html)});
    #             """
    #         )
    #
    #     return "\n".join(js)

    # def _leaflet_markers_js(self, matches):
    #     js = []
    #
    #     for idx, m in enumerate(matches, start=1):
    #         popup_html = (
    #             f"<b>#{idx}</b> {m.get('name', '')}<br>"
    #             f"Score: {m.get('final_score', 0)}"
    #         )
    #
    #         js.append(
    #             f"""
    #             const icon_{idx} = L.divIcon({{
    #                 className: '',
    #                 html: '<div class="marker-numbered"><span>{idx}</span></div>',
    #                 iconSize: [30, 30],
    #                 iconAnchor: [15, 30],
    #                 popupAnchor: [0, -30]
    #             }});
    #
    #             const marker_{idx} = L.marker(
    #                 [{m['lat']}, {m['lon']}],
    #                 {{
    #                     icon: icon_{idx},
    #                     matchIndex: {idx - 1}
    #                 }}
    #             )
    #             .addTo(map)
    #             .bindPopup({json.dumps(popup_html)});
    #             """
    #         )
    #
    #     return "\n".join(js)

    def _leaflet_markers_js(self, matches):
        js = []
        js.append("const allMarkers = [originalMarker];")  # array to store all markers

        for idx, m in enumerate(matches, start=1):
            popup_html = (
                f"<b>#{idx}</b> {m.get('name', '')}<br>"
                f"Score: {m.get('final_score', 0)}"
            )

            js.append(
                f"""
                const icon_{idx} = L.divIcon({{
                    className: '',
                    html: '<div class="marker-base marker-numbered"><span>{idx}</span></div>',
                    iconSize: [30, 30],
                    iconAnchor: [15, 30],
                    popupAnchor: [0, -30]
                }});

                const marker_{idx} = L.marker(
                    [{m['lat']}, {m['lon']}],
                    {{
                        icon: icon_{idx},
                        matchIndex: {idx - 1}
                    }}
                ).addTo(map)
                 .bindPopup({json.dumps(popup_html)});
                 
                 // Add marker to array for later bounds calculation
                allMarkers.push(marker_{idx});

                marker_{idx}.on('click', function() {{
                    if (window.bridge) {{
                        bridge.on_marker_clicked(this.options.matchIndex);
                    }}
                }});
                """
            )

        # Fit map to include all markers
        js.append("""
            if (allMarkers.length > 0) {
                const group = L.featureGroup(allMarkers);
                map.fitBounds(group.getBounds().pad(0.1)); // 10% padding
            }
        """)

        return "\n".join(js)

    def load_map(self, center_lat, center_lon, matches):
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
          <meta charset="utf-8" />
          <style>
          html, body, #map {{ height: 100%; margin: 0; }}
          .marker-base {{
              background-color: #277fca;
              border-radius: 50% 50% 50% 0;
              width: 30px;
              height: 30px;
              transform: rotate(-45deg);
              border: 1px solid #2e6c97;
              text-align: center;
              color: white;
              font-weight: bold;
              line-height: 26px;
              font-size: 14px;
            }}
            
            .marker-base span {{
              transform: rotate(45deg);
              display: block;
            }}
            
            /* Variant 1 */
            .marker-numbered {{
                background-color: #277fca;
                border: 1px solid #2e6c97;
            }}
            
            /* Variant 2 */
            .marker-original {{
                background-color: #cc2a3d;
                border: 1px solid #982e40;
            }}
          </style>
          <link
            rel="stylesheet"
            href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"
          />
          <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
        </head>
        <body>
          <div id="map"></div>
          <script src="qrc:///qtwebchannel/qwebchannel.js"></script>
          <script>
            new QWebChannel(qt.webChannelTransport, function(channel) {{
            window.bridge = channel.objects.bridge;
          }});
        </script>
          <script>
            const map = L.map('map').setView([{center_lat}, {center_lon}], 17);

            L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
              maxZoom: 19
            }}).addTo(map);

            // Original GeoJSON point
            const icon_org = L.divIcon({{
                className: '',
                html: '<div class="marker-base marker-original"><span>O</span></div>',
                iconSize: [30, 30],
                iconAnchor: [15, 30],
                popupAnchor: [0, -30]
            }});
                
            const originalMarker = L.marker([{center_lat}, {center_lon}], {{
              icon: icon_org
            }}).addTo(map).bindPopup("Original location");

            // Matched OSM places
            {self._leaflet_markers_js(matches)}
          </script>
        </body>
        </html>
        """
        self.map_view.setHtml(html)

    def update_matches_table(self, places):
        """
        places: list of OSM candidates (dicts) returned by search_places_around
                and enriched by find_best_place_match logic
        """
        # Rank by final_score
        places = sorted(
            places,
            key=lambda p: p.get("final_score", 0),
            reverse=True,
        )

        self.matches_table.setRowCount(0)

        for row, p in enumerate(places):
            self.matches_table.insertRow(row)

            values = [
                p.get("name", ""),
                # f"{p['lat']:.6f}",
                # f"{p['lon']:.6f}",
                # p.get("name_score", 0),
                p.get("distance_m", 0),
                # 1 - (p.get("distance_m", 0) / 50),  # or store directly
                p.get("final_score", 0),
            ]

            for col, val in enumerate(values):
                item = QTableWidgetItem(str(val))
                if col >= 3:
                    item.setTextAlignment(Qt.AlignCenter)
                self.matches_table.setItem(row, col, item)

    def set_matching_original_loc(self, name, lat, lon):
        self.label_matching_name.setText(f"{name} ({lat}, {lon})")
        # self.label_matching_lat.setText(f"Lat: {lat}")
        # self.label_matching_lon.setText(f"Lon: {lon}")

    def reset_matching(self):
        self.matches_select_button.setEnabled(False)
        self.org_loc_select_button.setEnabled(False)
        self.button_trigger_original.setEnabled(False)
        self.button_decrease_range.setEnabled(False)
        self.button_increase_range.setEnabled(False)

        self.matches_table.setRowCount(0)
        self.map_view.setHtml("")
        self.label_matching_name.setText("")

    # def set_running_state(self, run_state: str):
    #     super().set_running_state(run_state)
    #     if run_state == RunStates.FINISHED:
    #         self.matches_table.setRowCount(0)
    #         self.map_view.setHtml("")

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------
    def execute(self):
        self.emitter.status.emit(RunStates.RUNNING)

        # Runs scraping for each file
        for input_file_path in self.source_files:
            if self.osm_matcher.stop_requested:
                break

            if os.path.isdir(self.target_location):
                target_file_name = f"{os.path.splitext(os.path.basename(input_file_path))[0]}.kml"
                output_file_path = os.path.join(self.target_location, target_file_name)
            else:
                output_file_path = self.target_location

            try:
                threshold = float(self.threshold_entry.text())
            except ValueError:
                if self.matching_method == MatchingMethods.THRESHOLD:
                    threshold = DEFAULT_THRESHOLD
                    log.warning(f"No valid threshold provided, using default: {DEFAULT_THRESHOLD}")
                else:
                    threshold = None

            log.info(f"Matching method: {self.matching_method}")

            self.osm_matcher.process_places_to_kml(input_file_path=input_file_path,
                                  output_file_path=output_file_path,
                                  overwrite_output=self.overwrite_target,
                                  match_method=self.matching_method,
                                  threshold=threshold)

        self.emitter.status.emit(RunStates.FINISHED)

    def closeEvent(self, event):
        self.set_running_state(RunStates.STOPPED)

        # tell matcher to stop on next loop
        self.osm_matcher.stop_requested = True

        # in case the worker thread is currently waiting for input, return exit request
        if self.match_selection_loop is not None:
            self.selected_match = Commands.EXIT
            self.match_selection_loop.quit()
            self.match_selection_loop = None

        # call parent to wait for thread to stop
        super().closeEvent(event)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = OSMGeoProApp()
    window.show()
    sys.exit(app.exec_())
