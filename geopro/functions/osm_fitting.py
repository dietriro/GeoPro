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

from geopro.config import PATH_BOOKMARK_ICONS, PATH_PLACE_MAPPING
from geopro.functions.places_feature_matching import parse_mapcss, leave_longest_types, OsmTag, \
    convert_list_to_feature_types

log = logging.getLogger("geopro")
log.setLevel(logging.DEBUG)

NAME_WEIGHT = 0.7
DIST_WEIGHT = 0.3
RADIUS = 1000
TIMEOUT = 100
ALLOW_SELF_SIGNED_CERT = False

MWM_NS = "https://comaps.app"  # The namespace for mwm
NSMAP = {"mwm": MWM_NS}

OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    # "https://overpass.nchc.org.tw/api/interpreter",
]

place_matching_rules = None
data_place_icons = None

if ALLOW_SELF_SIGNED_CERT:
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class MatchingMethods:
    ALL = "all"
    BEST = "best"
    THRESHOLD = "threshold"


def extract_words(place_name: str) -> list:
    """
    Extract words from a place name while preserving internal apostrophes.
    """
    return re.findall(r"[A-Za-z]+(?:'[A-Za-z]+)?", place_name)


def overpass_request(
    query: str,
    timeout: int = 30,
    max_retries: int = 5,
):
    for attempt in range(1, max_retries + 1):
        url = random.choice(OVERPASS_ENDPOINTS)

        try:
            response = requests.post(
                url,
                data=query,
                timeout=timeout,
                headers={"Accept": "application/json"},
                verify=not ALLOW_SELF_SIGNED_CERT
            )

            if response.status_code in (429, 504):
                raise requests.exceptions.HTTPError(
                    f"{response.status_code} from Overpass"
                )

            response.raise_for_status()

            if "application/json" not in response.headers.get("Content-Type", ""):
                raise ValueError("Non-JSON Overpass response")

            return response.json()

        except Exception as e:
            wait = min(2 ** attempt, 30)
            log.warning(
                f"Overpass failed (attempt {attempt}/{max_retries}): {e}. "
                f"Retrying in {wait}s"
            )
            time.sleep(wait)

    log.error("Overpass permanently failed after retries")
    return None


def search_places_around(
    lat: float,
    lon: float,
    radius: int,
    place_name: str,
    place_type: str = "node",
    timeout: int = TIMEOUT,
):
    """
    Search for OSM nodes around given coordinates whose name approximately
    matches any word from place_name.

    Parameters:
        lat (float): latitude
        lon (float): longitude
        radius (int): search radius in meters
        place_name (str): name to match (split by spaces)
        timeout (int): request timeout in seconds

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
    [out:json][timeout:{timeout}];
    {place_type}
      ["name"~"{name_regex}", i]
      (around:{radius},{lat},{lon});
    out;
    """

    # print(query)

    data = overpass_request(query, timeout=timeout)

    if data is None:
        return None

    # log.debug(f"Search response data: {data}")

    results = []
    for el in data.get("elements", []):
        tags = el.get("tags", {})
        results.append({
            "id": el.get("id"),
            "name": tags.get("name"),
            "amenity": tags.get("amenity"),
            "lat": el.get("lat"),
            "lon": el.get("lon"),
            "original_tags": tags
        })

    return results

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

def find_best_place_match(
    places: list,
    target_lat: float,
    target_lon: float,
    target_name: str,
    max_distance: float = 5000.0,
):
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

    ranked_matches = []

    for place in places:
        lat = place.get("lat")
        lon = place.get("lon")

        if lat is None or lon is None:
            continue

        distance = haversine_distance(
            target_lat, target_lon,
            lat, lon
        )

        if distance > max_distance:
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
            name_score * NAME_WEIGHT
            + distance_score * DIST_WEIGHT
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

def write_to_kml(kml_obj, place_name, place_lat, place_lon, place_desc, icon_name=None, feature_types=None):
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
    kml_obj.Document.append(placemark)

def load_place_matching_data():
    place_mapping_file = Path(PATH_PLACE_MAPPING)

    if not place_mapping_file.exists():
        raise FileNotFoundError(place_mapping_file)

    with place_mapping_file.open("r", encoding="utf-8") as f:
        return parse_mapcss(f)

def get_place_features(place_data):
    """
    Find the matching icon name for a place based on its OSM tags
    and the bookmark icon YAML mapping.

    Returns:
        str, list | None, None  (e.g. "Bar", "Building", ...)
    """
    global place_matching_rules

    if place_matching_rules is None:
        place_matching_rules = load_place_matching_data()

    tags = place_data.get("original_tags", {})
    osm_tags = [OsmTag(key, value) for key, value in tags.items()]

    matched_types = list()
    for type_strings, rule in place_matching_rules:
        if rule.matches(osm_tags):
            matched_types.append(type_strings)

    feature_types_list = leave_longest_types(matched_types)
    feature_types = convert_list_to_feature_types(feature_types_list)

    log.debug(f"Identified feature-types: {feature_types}")

    return feature_types

def get_place_icon(place_data, bookmark_icon_file=PATH_BOOKMARK_ICONS):
    """
    Find the matching icon name for a place based on its OSM tags
    and the bookmark icon YAML mapping.

    Returns:
        str, list | None, None  (e.g. "Bar", "Building", ...)
    """
    global data_place_icons

    if data_place_icons is None:
        bookmark_icon_file = Path(bookmark_icon_file)

        if not bookmark_icon_file.exists():
            raise FileNotFoundError(bookmark_icon_file)

        with bookmark_icon_file.open("r", encoding="utf-8") as f:
            icon_map = yaml.safe_load(f) or {}

    tags = place_data.get("original_tags", {})
    if not isinstance(tags, dict):
        return None

    # Iterate in YAML order to preserve priority
    for category, submap in icon_map.items():
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

def process_places_to_kml(
        input_file_path: str,
        output_file_path: str,
        overwrite_output: bool,
        update_function: Callable[[str, int, int], None],
        user_match_selection: Callable[[str, float, float, list], None],
        match_method: str = MatchingMethods.BEST,
        threshold: float = None,
        include_skipped: bool = True
):
    successful = 0
    skipped = 0
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
    kml_obj = KML.kml(
        KML.Document(
        )
    )

    # ---------------------------------------------------------
    # Main processing loop
    # ---------------------------------------------------------
    for idx, feature in enumerate(features, start=1):
        try:
            properties = feature.get("properties", {})
            geometry = feature.get("geometry", {})
            coordinates = geometry.get("coordinates")

            if not coordinates or geometry.get("type") != "Point":
                skipped += 1
                log.warning(f"Skipping feature {idx}: invalid geometry")
                continue

            lon, lat = coordinates
            place_name = properties.get("name", "Unknown")
            place_desc = properties.get("description", "")

            log.info(f"[{idx}/{len(features)}] Matching place: {place_name}")
            log.debug(f"Source Data: {lat, lon, RADIUS, place_name}")

            # ---- correct call ----
            candidates = search_places_around(
                lat=lat,
                lon=lon,
                radius=RADIUS,
                place_name=place_name,
                place_type="node"
            )

            log.debug(f"Candidates: {candidates}")

            if not candidates:
                skipped += 1
                log.warning(f"No OSM candidates found for '{place_name}'")
                write_to_kml(kml_obj, place_name, lat, lon, place_desc)
                update_function(input_file_path, successful, skipped)
                continue

            # ---- correct call & return handling ----
            ranked_matches = find_best_place_match(
                places=candidates,
                target_lat=lat,
                target_lon=lon,
                target_name=place_name,
            )

            if not ranked_matches:
                skipped += 1
                log.warning(f"No suitable OSM match for '{place_name}'")
                write_to_kml(kml_obj, place_name, lat, lon, place_desc)
                update_function(input_file_path, successful, skipped)
                continue

            if match_method == MatchingMethods.BEST:
                best_match = ranked_matches[0]
            elif match_method == MatchingMethods.THRESHOLD:
                if threshold is None:
                    skipped += 1
                    log.warning(f"No suitable OSM match for '{place_name}'")
                    write_to_kml(kml_obj, place_name, lat, lon, place_desc)
                    update_function(input_file_path, successful, skipped)
                    continue

                score = ranked_matches[0].get("final_score", 0.0)
                if score >= threshold:
                    best_match = ranked_matches[0]
                    log.debug(f"Best match score is above threshold: {score} >= {threshold}. Using best match.")
                else:
                    log.debug(f"Best match score is below threshold: {score} < {threshold}. Requiring user input.")
                    selection = user_match_selection(place_name, lat, lon, ranked_matches)
                    if selection == -1:
                        # original location selected
                        log.debug("Matching: User selected original location.")
                        successful += 1
                        write_to_kml(kml_obj, place_name, lat, lon, place_desc)
                        update_function(input_file_path, successful, skipped)
                        continue
                    best_match = ranked_matches[selection]

                    log.info(f"User selection: {selection}")
            elif match_method == MatchingMethods.ALL:
                # test waiting for button input
                selection = user_match_selection(place_name, lat, lon, ranked_matches)
                log.info(f"User selection: {selection}")
                if selection == -1:
                    # original location selected
                    log.debug("Matching: User selected original location.")
                    successful += 1
                    write_to_kml(kml_obj, place_name, lat, lon, place_desc)
                    update_function(input_file_path, successful, skipped)
                    continue

                best_match = ranked_matches[selection]

                log.info(f"User selection: {selection}")
            else:
                log.error(f"Match method not supported: {match_method}")
                continue

            # determine icon for best match
            icon_name = get_place_icon(best_match)
            feature_types = get_place_features(best_match)

            score = best_match.get("final_score", 0.0)
            scores.append(score)

            osm_lat = best_match["lat"]
            osm_lon = best_match["lon"]
            osm_name = best_match.get("name", place_name)

            successful += 1

            write_to_kml(kml_obj, osm_name, osm_lat, osm_lon, place_desc,
                         icon_name=icon_name, feature_types=feature_types)

        except Exception as e:
            skipped += 1
            log.exception(f"Error processing location {idx}: {e}")

        # -----------------------------------------------------
        # Update AFTER each feature
        # -----------------------------------------------------
        update_function(input_file_path, successful, skipped)

    # ---------------------------------------------------------
    # Finalize KML
    # ---------------------------------------------------------
    try:
        with open(output_file_path, "wb") as f:
            f.write(etree.tostring(kml_obj, pretty_print=True, xml_declaration=True, encoding="UTF-8"))
    except Exception as e:
        log.error(f"Failed to finalize KML file: {e}")

    avg_score = sum(scores) / len(scores) if scores else 0.0
    log.info(
        f"Finished processing {input_file_path}: "
        f"{successful} matched, {skipped} skipped, "
        f"avg score={avg_score:.3f}"
    )

    # Final UI sync
    update_function(input_file_path, successful, skipped)
