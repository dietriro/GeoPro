import os

from dataclasses import dataclass
from typing import List

import geopro

package_path = os.path.dirname(os.path.dirname(geopro.__file__))

class Animations:
    COMPLETED = os.path.join(package_path, "resources/completed.gif")
    MATCHING = os.path.join(package_path, "resources/matching.gif")
    GEOLOCATION = os.path.join(package_path, "resources/geolocation.gif")


@dataclass(frozen=True)
class FileType:
    name: str
    extensions: List[str]

    @property
    def dialog_filter(self) -> str:
        return f"{self.name} ({' '.join('*' + e for e in self.extensions)})"


class FileTypeConfig:
    CSV = FileType("CSV Files", [".csv"])
    JSON = FileType("JSON Files", [".json"])
    GEOJSON = FileType("GeoJSON Files", [".geojson"])
    KML = FileType("KML Files", [".kml"])

    @classmethod
    def dialog_filter(cls, *types: FileType) -> str:
        return ";;".join(t.dialog_filter for t in types)


class RunStates:
    INIT = "initialized"
    RUNNING = "running"
    FINISHED = "finished"
    USER_INPUT = "user_input"