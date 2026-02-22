import requests
import re
import math
import logging
import os
import json
import random
import time
import yaml
import urllib3

from pathlib import Path
from typing import Callable
from pykml.factory import KML_ElementMaker as KML
from lxml import etree

from geopro.config import PATH_BOOKMARK_ICONS, PATH_PLACE_MAPPING, RANGES, DEFAULT_RANGE, Commands, UserSelection
from geopro.functions.places_feature_matching import parse_mapcss, leave_longest_types, OsmTag, \
    convert_list_to_feature_types

log = logging.getLogger("geopro")
log.setLevel(logging.DEBUG)

MWM_NS = "https://comaps.app"  # The namespace for mwm
NSMAP = {"mwm": MWM_NS}

OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    # "https://overpass.nchc.org.tw/api/interpreter",
]


class MatchingMethods:
    ALL = "all"
    BEST = "best"
    THRESHOLD = "threshold"


class DuplicateError(Exception):
    pass


def haversine_distance(lat1, lon1, lat2, lon2):
    R = 6371000  # Earth radius in meters
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)

    a = (
            math.sin(dphi / 2) ** 2
            + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    )
    return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1 - a))

def extract_words(place_name: str) -> list:
    """
    Extract words from a place name while preserving internal apostrophes.
    """
    return re.findall(r"[A-Za-z]+(?:'[A-Za-z]+)?", place_name)

def name_overlap_score(name_a: str, name_b: str) -> float:
    def normalize(name):
        return {
            w.lower()
            for w in re.split(r"\W+", name)
            if len(w) > 2
        }

    set_a = normalize(name_a)
    set_b = normalize(name_b)

    if not set_a or not set_b:
        return 0.0

    intersection = set_a & set_b
    union = set_a | set_b

    return len(intersection) / len(union)


class OSMMatcher:
    def __init__(self, update_function: Callable[[str, int, int], None],
                 user_match_selection: Callable[[str, float, float, list, int], None],
                 range=None, name_weight=0.7, dist_weight=0.3, timeout=100, allow_self_signed_cert=True):
        if range is None:
            self.range = DEFAULT_RANGE
        else:
            self.range = range

        self.name_weight = name_weight
        self.dist_weight = dist_weight
        self.timeout = timeout
        self.allow_self_signed_cert = allow_self_signed_cert

        self.update_function = update_function
        self.user_match_selection = user_match_selection

        self.kml_obj = None
        self.place_matching_rules = None
        self.data_place_icons = None
        self.successful = None
        self.skipped = None

        self.stop_requested = False

        if allow_self_signed_cert:
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

        self.load_place_matching_data()
        self.load_icon_data()

    def load_place_matching_data(self):
        place_mapping_file = Path(PATH_PLACE_MAPPING)

        if not place_mapping_file.exists():
            raise FileNotFoundError(place_mapping_file)

        with place_mapping_file.open("r", encoding="utf-8") as f:
            self.place_matching_rules = parse_mapcss(f)

    def load_icon_data(self):
        bookmark_icon_file = Path(PATH_BOOKMARK_ICONS)

        if not bookmark_icon_file.exists():
            raise FileNotFoundError(bookmark_icon_file)

        with bookmark_icon_file.open("r", encoding="utf-8") as f:
            self.data_place_icons = yaml.safe_load(f) or {}

    def overpass_request(self, query: str, timeout: int = 30, max_retries: int = 5):
        for attempt in range(1, max_retries + 1):
            url = random.choice(OVERPASS_ENDPOINTS)

            try:
                response = requests.post(
                    url,
                    data=query,
                    timeout=timeout,
                    headers={"Accept": "application/json"},
                    verify=not self.allow_self_signed_cert
                )

                if response.status_code in (429, 504):
                    raise requests.exceptions.HTTPError(
                        f"{response.status_code} from Overpass"
                    )

                response.raise_for_status()

                if "application/json" not in response.headers.get("Content-Type", ""):
                    if "duplicate_query" in response.text:
                        raise DuplicateError("Duplicate query")
                    else:
                        raise ValueError("Non-JSON Overpass response")

                return response.json()

            except DuplicateError as e:
                log.warning(
                    f"Overpass failed (attempt {attempt}/{max_retries}): {e}. "
                    f"Not retrying because of duplicate query."
                )
                break
            except Exception as e:
                wait = min(2 ** attempt, 30)
                log.warning(
                    f"Overpass failed (attempt {attempt}/{max_retries}): {e}. "
                    f"Retrying in {wait}s"
                )
                time.sleep(wait)

        log.error("Overpass permanently failed after retries")
        return None

    def search_places_around(self, lat: float, lon: float, place_name: str, place_type: str = "node"):
        """
        Search for OSM nodes around given coordinates whose name approximately
        matches any word from place_name.
    
        Parameters:
            lat (float): latitude
            lon (float): longitude
            place_type: Type of the place [node, way, collection]
            place_name (str): name to match (split by spaces)
        Returns:
            list[dict]: list of places with name, coordinates, amenity, and id
        """
    
        # Split name into words, remove short/noisy tokens
        words = extract_words(place_name)
    
        if not words:
            return []
    
        # Build OR regex: word1|word2|word3
        name_regex = "|".join(words)
    
        # Overpass QL query (nodes only)
        query = f"""
        [out:json][timeout:{self.timeout}];
        {place_type}
          ["name"~"{name_regex}", i]
          (around:{self.range},{lat},{lon});
        out center;
        """
    
        # print(query)
    
        data = self.overpass_request(query, timeout=self.timeout)
    
        if data is None:
            return None
    
        # log.debug(f"Search response data: {data}")
    
        results = []
        for el in data.get("elements", []):
            tags = el.get("tags", {})

            # retrieve lat/lon
            lat = el.get("lat")
            lon = el.get("lon")
            if lat is None or lon is None:
                center = el.get("center", None)
                if center is None or ("lat" not in center.keys() and "lon" not in center.keys()):
                    log.debug("Couldn't find lat and lon for place.")
                    continue
                lat = center.get("lat")
                lon = center.get("lon")

            results.append({
                "id": el.get("id"),
                "name": tags.get("name"),
                "amenity": tags.get("amenity"),
                "lat": lat,
                "lon": lon,
                "original_tags": tags
            })
    
        return results

    def rank_matched_places(self, places: list, target_lat: float, target_lon: float, target_name: str,
                            max_distance: float = None):
        """
        Rank OSM places by likelihood of matching the target place.
    
        Parameters:
            places (list[dict]): output from search_places_around()
            target_lat (float): reference latitude
            target_lon (float): reference longitude
            target_name (str): original place name
            max_distance (float): maximum acceptable distance in meters
    
        Returns:
            list[dict]: ranked list of matched places (best first)
        """
    
        if not places:
            return []

        if max_distance is None:
            max_distance = self.range * 2
    
        ranked_matches = []
    
        for place in places:
            lat = place.get("lat")
            lon = place.get("lon")
    
            if lat is None or lon is None:
                log.debug("Lat or lon are none for place")
                continue

            distance = haversine_distance(
                target_lat, target_lon,
                lat, lon
            )
    
            if distance > max_distance:
                log.debug("Distance is larger than max distance")
                continue
    
            # Normalize distance score (closer = better)
            distance_score = max(0.0, 1.0 - (distance / max_distance))
    
            log.debug(f"Distance score: {distance_score}")
    
            name_score = name_overlap_score(
                target_name,
                place.get("name", "")
            )
    
            log.debug(f"Name score: {name_score}")
    
            final_score = (
                name_score * self.name_weight
                + distance_score * self.dist_weight
            )
    
            ranked_matches.append({
                **place,
                "distance_m": round(distance, 2),
                "distance_score": round(distance_score, 3),
                "name_score": round(name_score, 3),
                "final_score": round(final_score, 3),
            })
    
        # Sort by total score (best first)
        ranked_matches.sort(
            key=lambda p: p["final_score"],
            reverse=True,
        )
    
        return ranked_matches
    
    def write_to_kml(self, place_name, place_lat, place_lon, place_desc, icon_name=None, feature_types=None):
        # Create the ExtendedData element with mwm namespace
        extdata = etree.Element("{http://www.opengis.net/kml/2.2}ExtendedData", nsmap=NSMAP)
    
        # Add the mwm:icon element only if icon_name is provided
        if icon_name:
            icon_el = etree.SubElement(extdata, f"{{{MWM_NS}}}icon")
            icon_el.text = icon_name
    
        # Add mwm:featureTypes block if feature_types are provided
        if feature_types:
            feature_types_el = etree.SubElement(
                extdata, f"{{{MWM_NS}}}featureTypes"
            )
            for ft in feature_types:
                value_el = etree.SubElement(
                    feature_types_el, f"{{{MWM_NS}}}value"
                )
                value_el.text = ft
    
        # Create the Placemark
        placemark = KML.Placemark(
            KML.name(place_name),
            KML.description(place_desc),
            KML.Point(KML.coordinates(f"{place_lon},{place_lat},0")),
            extdata
        )
    
        # Append to the Document element
        self.kml_obj.Document.append(placemark)

    def get_place_features(self, place_data):
        """
        Find the matching icon name for a place based on its OSM tags
        and the bookmark icon YAML mapping.
    
        Returns:
            str, list | None, None  (e.g. "Bar", "Building", ...)
        """
        tags = place_data.get("original_tags", {})
        osm_tags = [OsmTag(key, value) for key, value in tags.items()]
    
        matched_types = list()
        for type_strings, rule in self.place_matching_rules:
            if rule.matches(osm_tags):
                matched_types.append(type_strings)
    
        feature_types_list = leave_longest_types(matched_types)
        feature_types = convert_list_to_feature_types(feature_types_list)
    
        log.debug(f"Identified feature-types: {feature_types}")
    
        return feature_types
    
    def get_place_icon(self, place_data):
        """
        Find the matching icon name for a place based on its OSM tags
        and the bookmark icon YAML mapping.
    
        Returns:
            str, list | None, None  (e.g. "Bar", "Building", ...)
        """
        tags = place_data.get("original_tags", {})
        if not isinstance(tags, dict):
            return None
    
        # Iterate in YAML order to preserve priority
        for category, submap in self.data_place_icons.items():
            if category not in tags:
                continue
    
            value = tags.get(category)
            if not value:
                continue
    
            # OSM values already use underscores, so no normalization needed
            if value in submap:
                return submap[value]
    
            if "default" in submap:
                return submap["default"]
    
        return None
    
    def set_radius_from_string(self, input_str):
        try:
            if input_str == Commands.ZOOM_OUT:
                new_index = RANGES.index(self.range) + 1
                if new_index >= len(RANGES):
                    log.warning(f"Selected range not valid. Using default range: {DEFAULT_RANGE}")
                    self.range = DEFAULT_RANGE
                self.range = RANGES[new_index]
            elif input_str == Commands.ZOOM_IN:
                new_index = RANGES.index(self.range) - 1
                if new_index < 0:
                    log.warning(f"Selected range not valid. Using default range: {DEFAULT_RANGE}")
                    self.range = DEFAULT_RANGE
                self.range = RANGES[new_index]
            elif input_str == Commands.EXIT:
                return False
            else:
                log.warning(f"Unknown return value for result. Using default range: {DEFAULT_RANGE}")
                self.range = DEFAULT_RANGE
        except IndexError as e:
            log.debug(e)
            log.warning(f"Invalid range selection. Using default range: {DEFAULT_RANGE}")
            self.range = DEFAULT_RANGE
        return True

    def handle_empty_osm_data(self, lat, lon, place_name, place_desc, match_method, input_file_path):
        log.warning(f"No OSM candidates found for '{place_name}'")

        if match_method == MatchingMethods.BEST:
            self.skipped += 1
            self.write_to_kml(place_name, lat, lon, place_desc)
            self.update_function(input_file_path, self.successful, self.skipped)
            return False
        else:
            selection = self.user_match_selection(place_name, lat, lon, list(), self.range)
            if type(selection) is str:
                # new radius was chosen
                if not self.set_radius_from_string(selection):
                    raise ValueError(f"An invalid radius was chosen: {selection}")
                return True
            elif type(selection) is int and selection == -1:
                # original place was selected
                log.debug("Matching: User selected original location.")
                self.successful += 1
            else:
                log.warning(f"Selection made by user is not valid: '{selection}'. "
                            f"Falling back to original location.")
                self.skipped += 1
            self.write_to_kml(place_name, lat, lon, place_desc)
            self.update_function(input_file_path, self.successful, self.skipped)
            return False

    def retrieve_user_selection(self, lat, lon, place_name, place_desc, ranked_matches, input_file_path):
        selection = self.user_match_selection(place_name, lat, lon, ranked_matches, self.range)
        log.debug(f"User selection: {selection}")
        if type(selection) is str:
            # new radius was chosen
            if not self.set_radius_from_string(selection):
                return UserSelection.EXIT, selection
            return UserSelection.NEW_RADIUS, selection
        elif type(selection) is int and selection >= 0:
            return UserSelection.VALID_ITEM, selection
        else:
            if type(selection) is int and selection == -1:
                # original place was selected
                log.debug("Matching: User selected original location.")
                self.successful += 1
            else:
                log.warning(f"Selection made by user is not valid: '{selection}'. "
                            f"Falling back to original location.")
                self.skipped += 1
            self.write_to_kml(place_name, lat, lon, place_desc)
            self.update_function(input_file_path, self.successful, self.skipped)
            return UserSelection.OTHER_ITEM, selection


    def process_places_to_kml(self, input_file_path: str, output_file_path: str, overwrite_output: bool,
                              match_method: str = MatchingMethods.BEST, threshold: float = None,
                              include_skipped: bool = True):
        self.successful = 0
        self.skipped = 0
        scores = []
    
        # ---------------------------------------------------------
        # Validate paths
        # ---------------------------------------------------------
        if not os.path.isfile(input_file_path):
            log.error(f"Input file does not exist: {input_file_path}")
            return
    
        if os.path.exists(output_file_path) and not overwrite_output:
            log.info(f"Output file exists and overwrite is disabled: {output_file_path}")
            return
    
        if not match_method in [MatchingMethods.BEST, MatchingMethods.THRESHOLD, MatchingMethods.ALL]:
            log.error(f"Matching method not valid: {match_method}")
    
        # ---------------------------------------------------------
        # Load input file
        # ---------------------------------------------------------
        try:
            with open(input_file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            log.error(f"Failed to read input file {input_file_path}: {e}")
            return
    
        if data.get("type") != "FeatureCollection":
            log.error("Input file is not a GeoJSON FeatureCollection")
            return
    
        features = data.get("features", [])
        log.info(f"Processing {len(features)} places from {input_file_path}")
    
        # ---------------------------------------------------------
        # Prepare KML output
        # ---------------------------------------------------------
        self.kml_obj = KML.kml(
            KML.Document(
            )
        )
    
        # ---------------------------------------------------------
        # Main processing loop
        # ---------------------------------------------------------
        for idx, feature in enumerate(features, start=1):
            if self.stop_requested:
                log.warning(f"Stop requested. Terminating now.")
                return

            self.range = DEFAULT_RANGE

            try:
                properties = feature.get("properties", {})
                geometry = feature.get("geometry", {})
                coordinates = geometry.get("coordinates")
    
                if not coordinates or geometry.get("type") != "Point":
                    self.skipped += 1
                    log.warning(f"Skipping feature {idx}: invalid geometry")
                    continue
    
                lon, lat = coordinates
                place_name = properties.get("name", "Unknown")
                place_desc = properties.get("description", "")
    
                match_successful = False
    
                while not match_successful:
                    log.info(f"[{idx}/{len(features)}] Matching place: {place_name}")
                    log.debug(f"Source Data: {lat, lon, self.range, place_name}")
    
                    # ---- correct call ----
                    candidates = self.search_places_around(
                        lat=lat,
                        lon=lon,
                        place_name=place_name,
                        place_type="nwr"
                    )
    
                    log.debug(f"Candidates: {candidates}")
    
                    if not candidates:
                        if self.handle_empty_osm_data(lat, lon, place_name, place_desc, match_method, input_file_path):
                            continue
                        else:
                            break
    
    
                    # ---- correct call & return handling ----
                    ranked_matches = self.rank_matched_places(
                        places=candidates,
                        target_lat=lat,
                        target_lon=lon,
                        target_name=place_name,
                    )
    
                    if not candidates:
                        if self.handle_empty_osm_data(lat, lon, place_name, place_desc, match_method, input_file_path):
                            continue
                        else:
                            break
    
                    if match_method == MatchingMethods.BEST:
                        best_match = ranked_matches[0]
                    elif match_method == MatchingMethods.THRESHOLD:
                        if threshold is None:
                            self.skipped += 1
                            log.warning(f"No suitable OSM match for '{place_name}'")
                            self.write_to_kml(place_name, lat, lon, place_desc)
                            self.update_function(input_file_path, self.successful, self.skipped)
                            break
    
                        score = ranked_matches[0].get("final_score", 0.0)
                        if score >= threshold:
                            best_match = ranked_matches[0]
                            log.debug(f"Best match score is above threshold: {score} >= {threshold}. Using best match.")
                        else:
                            log.debug(f"Best match score is below threshold: {score} < {threshold}. Requiring user input.")
                            user_choice, selection = self.retrieve_user_selection(lat, lon, place_name, place_desc,
                                                                                  ranked_matches, input_file_path)
                            if user_choice == UserSelection.NEW_RADIUS:
                                continue
                            elif user_choice == UserSelection.VALID_ITEM:
                                best_match = ranked_matches[selection]
                            elif user_choice == UserSelection.EXIT:
                                return
                            else:
                                break

                    elif match_method == MatchingMethods.ALL:
                        user_choice, selection = self.retrieve_user_selection(lat, lon, place_name, place_desc,
                                                                              ranked_matches, input_file_path)
                        if user_choice == UserSelection.NEW_RADIUS:
                            continue
                        elif user_choice == UserSelection.VALID_ITEM:
                            best_match = ranked_matches[selection]
                        elif user_choice == UserSelection.EXIT:
                            return
                        else:
                            break
                    else:
                        log.error(f"Match method not supported: {match_method}")
                        break
    
                    # determine icon for best match
                    icon_name = self.get_place_icon(best_match)
                    feature_types = self.get_place_features(best_match)
    
                    score = best_match.get("final_score", 0.0)
                    scores.append(score)
    
                    osm_lat = best_match["lat"]
                    osm_lon = best_match["lon"]
                    osm_name = best_match.get("name", place_name)
    
                    self.successful += 1
    
                    self.write_to_kml(osm_name, osm_lat, osm_lon, place_desc,
                                 icon_name=icon_name, feature_types=feature_types)
    
                    match_successful = True
    
            except Exception as e:
                self.skipped += 1
                log.exception(f"Error processing location {idx}: {e}")
    
            # -----------------------------------------------------
            # Update AFTER each feature
            # -----------------------------------------------------
            self.update_function(input_file_path, self.successful, self.skipped)
    
        # ---------------------------------------------------------
        # Finalize KML
        # ---------------------------------------------------------
        try:
            with open(output_file_path, "wb") as f:
                f.write(etree.tostring(self.kml_obj, pretty_print=True, xml_declaration=True, encoding="UTF-8"))
        except Exception as e:
            log.error(f"Failed to finalize KML file: {e}")
    
        avg_score = sum(scores) / len(scores) if scores else 0.0
        log.info(
            f"Finished processing {input_file_path}: "
            f"{self.successful} matched, {self.skipped} skipped, "
            f"avg score={avg_score:.3f}"
        )
    
        # Final UI sync
        self.update_function(input_file_path, self.successful, self.skipped)
