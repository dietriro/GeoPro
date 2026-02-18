import os
import logging
from dataclasses import dataclass
from enum import Enum

import geopro

log = logging.getLogger("geopro")
package_path = os.path.dirname(os.path.dirname(geopro.__file__))

PATH_RESOURCES = os.path.join(package_path, "resources")
PATH_BOOKMARK_ICONS = os.path.join(PATH_RESOURCES, "bookmark_icons.yaml")
PATH_PLACE_MAPPING = os.path.join(PATH_RESOURCES, "mapcss-mapping.csv")
PATH_CHROME = os.path.join(package_path, "chrome")

RANGES = [10, 30, 100, 1000, 5000]
DEFAULT_RANGE = 10

@dataclass(frozen=True)
class Animations:
    COMPLETED = "completed"
    MATCHING = "matching"
    GEOLOCATION = "geolocation"

    @staticmethod
    def get_path(animation):
        log.debug(f"Animation path: {os.path.join(package_path, f'{animation}_{RunningConfig.theme}.gif')}")
        return os.path.join(PATH_RESOURCES, f"{animation}_{RunningConfig.theme}.gif")

@dataclass(frozen=True)
class AnimationStates:
    PLAYING = "playing"
    STOPPED = "stopped"
    FRAME = "frame"

@dataclass(frozen=True)
class Icons:
    MARKER_MATCH = os.path.join(PATH_RESOURCES, "icon_marker_match.svg")
    MARKER_ORIGINAL = os.path.join(PATH_RESOURCES, "icon_marker_original.svg")


@dataclass(frozen=True)
class Themes:
    DARK = "dark"
    LIGHT = "light"


@dataclass(frozen=True)
class Commands:
    ZOOM_IN = "zoom-in"
    ZOOM_OUT = "zoom-out"
    EXIT = "exit"


class ColorRole(Enum):
    ACTIVE = "active"
    SKIPPED = "skipped"
    SUCCESS = "success"
    INIT = "init"


class Colors:
    TableBackground = {
        Themes.DARK: {
            ColorRole.ACTIVE:  "#8AB4F7",
            ColorRole.SKIPPED: "#A0721A",
            ColorRole.SUCCESS: "#6E9E70",
        },
        Themes.LIGHT: {
            ColorRole.ACTIVE:  "#BBDEFB",
            ColorRole.SKIPPED: "#FFF59D",
            ColorRole.SUCCESS: "#C8E6C9",
        },
    }


class RunningConfig:
    theme = Themes.DARK
    animation = None
    animation_state = None
