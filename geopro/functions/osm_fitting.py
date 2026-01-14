import requests
import re
import math
import logging
import os
import json
import random
import time
from typing import Callable

import simplekml

log = logging.getLogger("geopro")
log.setLevel(logging.DEBUG)

# OVERPASS_URL = "https://overpass-api.de/api/interpreter"
NAME_WEIGHT = 0.7
DIST_WEIGHT = 0.3
RADIUS = 1000
TIMEOUT = 100


OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    # "https://overpass.nchc.org.tw/api/interpreter",
]


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
    # words = [
    #     re.escape(w)
    #     for w in place_name.split()
    #     if len(w) > 2
    # ]

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

    print(query)

    # response = requests.post(
    #     OVERPASS_URL,
    #     data=query,
    #     timeout=timeout,
    #     headers={"Accept": "application/json"},
    # )
    # response.raise_for_status()

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
    Determine the most likely OSM place match.

    Parameters:
        places (list[dict]): output from search_places_around()
        target_lat (float): reference latitude
        target_lon (float): reference longitude
        target_name (str): original place name
        max_distance (float): maximum acceptable distance in meters

    Returns:
        dict | None: best matching place or None
    """

    if not places:
        return None

    best_score = 0.0
    best_place = None

    for place in places:
        if not place.get("lat") or not place.get("lon"):
            continue

        distance = haversine_distance(
            target_lat, target_lon,
            place["lat"], place["lon"]
        )

        if distance > max_distance:
            continue

        # Normalize distance score (closer = better)
        distance_score = 1.0 - (distance / max_distance)

        name_score = name_overlap_score(
            target_name,
            place.get("name", "")
        )

        final_score = (
            name_score * NAME_WEIGHT
            + distance_score * DIST_WEIGHT
        )

        if final_score > best_score:
            best_score = final_score
            best_place = {
                **place,
                "distance_m": round(distance, 2),
                "name_score": round(name_score, 3),
                "final_score": round(final_score, 3),
            }

    return best_place

def write_to_kml(kml_obj, place_name, place_lat, place_lon, place_desc):
    # kml_file.write(
    #     "  <Placemark>\n"
    #     f"    <name>{place_name}</name>\n"
    #     "    <Point>\n"
    #     f"      <coordinates>{osm_lon},{osm_lat},0</coordinates>\n"
    #     "    </Point>\n"
    #     "  </Placemark>\n"
    # )
    kml_obj.newpoint(
        name=place_name,
        description=place_desc,
        coords=[(place_lat, place_lon)]
    )

def process_places_to_kml(
    input_file_path: str,
    output_file_path: str,
    overwrite_output: bool,
    update_function: Callable[[str, int, int, float], None],
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
    # try:
    #     kml_file = open(output_file_path, "w", encoding="utf-8")
    #     kml_file.write(
    #         '<?xml version="1.0" encoding="UTF-8"?>\n'
    #         '<kml xmlns="http://www.opengis.net/kml/2.2">\n'
    #         "<Document>\n"
    #     )
    # except Exception as e:
    #     log.error(f"Failed to open output KML file: {e}")
    #     return
    kml_obj = simplekml.Kml()

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

            # if not candidates:
            #     log.debug("No candidates found in nodes, trying ways now.")
            #     candidates = search_places_around(
            #         lat=lat,
            #         lon=lon,
            #         radius=RADIUS,
            #         place_name=place_name,
            #         place_type="way"
            #     )
            #
            #     log.debug(f"Candidates (ways): {candidates}")

            if not candidates:
                skipped += 1
                log.warning(f"No OSM candidates found for '{place_name}'")
                write_to_kml(kml_obj, place_name, lat, lon, place_desc)
                continue

            # ---- correct call & return handling ----
            best_match = find_best_place_match(
                places=candidates,
                target_lat=lat,
                target_lon=lon,
                target_name=place_name,
            )

            if not best_match:
                skipped += 1
                log.warning(f"No suitable OSM match for '{place_name}'")
                write_to_kml(kml_obj, place_name, lat, lon, place_desc)
                continue

            successful += 1
            score = best_match.get("final_score", 0.0)
            scores.append(score)

            osm_lat = best_match["lat"]
            osm_lon = best_match["lon"]
            osm_name = best_match.get("name", place_name)

            write_to_kml(kml_obj, osm_name, osm_lat, osm_lon, place_desc)


        except Exception as e:
            skipped += 1
            log.exception(f"Error processing feature {idx}: {e}")

        # -----------------------------------------------------
        # Update AFTER each feature
        # -----------------------------------------------------
        avg_score = sum(scores) / len(scores) if scores else 0.0
        update_function(
            input_file_path,
            successful,
            skipped,
            round(avg_score, 4),
        )

    # ---------------------------------------------------------
    # Finalize KML
    # ---------------------------------------------------------
    try:
        kml_file.write("</Document>\n</kml>\n")
        kml_file.close()
    except Exception as e:
        log.error(f"Failed to finalize KML file: {e}")

    avg_score = sum(scores) / len(scores) if scores else 0.0
    log.info(
        f"Finished processing {input_file_path}: "
        f"{successful} matched, {skipped} skipped, "
        f"avg score={avg_score:.3f}"
    )

    # Final UI sync
    update_function(
        input_file_path,
        successful,
        skipped,
        round(avg_score, 4),
    )
