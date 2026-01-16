import os
from dataclasses import dataclass

import geopro

package_path = os.path.dirname(os.path.dirname(geopro.__file__))

PATH_RESOURCES = os.path.join(package_path, "resources")

@dataclass(frozen=True)
class Animations:
    COMPLETED = os.path.join(PATH_RESOURCES, "completed.gif")
    MATCHING = os.path.join(PATH_RESOURCES, "matching.gif")
    GEOLOCATION = os.path.join(PATH_RESOURCES, "geolocation.gif")

@dataclass(frozen=True)
class Icons:
    MARKER_MATCH = os.path.join(PATH_RESOURCES, "icon_marker_match.svg")
    MARKER_ORIGINAL = os.path.join(PATH_RESOURCES, "icon_marker_original.svg")
