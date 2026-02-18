from dataclasses import dataclass
from typing import List

from PyQt5.QtCore import QObject, pyqtSignal


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


class Emitter(QObject):
    status = pyqtSignal(str)
    set_processing_result = pyqtSignal(str, int, int)

class EmitterGMaps(Emitter):
    pass

class EmitterOSM(Emitter):
    user_match_selection = pyqtSignal(str, float, float, list, int)
    reset_matching = pyqtSignal()


class RunStates:
    INIT = "initialized"
    RUNNING = "running"
    FINISHED = "finished"
    USER_INPUT = "user_input"
    STOPPED = "stopped"