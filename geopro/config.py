import os
import logging
from dataclasses import dataclass

import geopro

log = logging.getLogger("geopro")
package_path = os.path.dirname(os.path.dirname(geopro.__file__))

PATH_RESOURCES = os.path.join(package_path, "resources")

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


class RunningConfig:
    theme = Themes.DARK
    animation = None
    animation_state = None
