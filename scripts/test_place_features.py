from pathlib import Path

from geopro.functions.places_feature_matching import OsmTag, leave_longest_types, parse_mapcss, convert_list_to_feature_types
from geopro.config import PATH_PLACE_MAPPING



tags_dict = {
    "addr:housenumber": "44",
    "addr:street": "Douglas Street",
    "amenity": "cafe",
    "building": "retail",
    "building:levels": "1",
    "indoor_seating": "yes",
    "name": "Heimish Bleu",
    "outdoor_seating": "yes"
}

tags_dict = {'bench': 'yes', 'bin': 'yes', 'bus': 'yes', 'highway': 'bus_stop', 'kerb': 'raised', 'kerb:height': '0.10', 'lit': 'yes', 'name': 'Münchner Freiheit', 'platform:width': '11.2', 'public_transport': 'platform', 'ref': '43', 'ref:IFOPT': 'de:09162:500:33:43', 'shelter': 'yes', 'tactile_paving': 'yes'}

# tags_dict = {'description': 'Münchner Freiheit, Stop Tram 23 Richtung Schwabing Nord und Ausstieg Tram 23 (Endhaltestelle)', 'local_ref': '1', 'name': 'Münchner Freiheit', 'operator': 'MVG', 'public_transport': 'stop_position', 'railway': 'stop', 'ref': '7', 'ref:IFOPT': 'de:09162:500:1:7', 'tram': 'yes', 'wheelchair': 'yes'}

tags = [OsmTag(key, value) for key, value in tags_dict.items()]

place_mapping_file = Path(PATH_PLACE_MAPPING)

if not place_mapping_file.exists():
    raise FileNotFoundError(place_mapping_file)

with place_mapping_file.open("r", encoding="utf-8") as f:
    rules = parse_mapcss(f)

matched_types = list()
for type_strings, rule in rules:
    if rule.matches(tags):
        matched_types.append(type_strings)

print(matched_types)

reduced_types = leave_longest_types(matched_types)

final_types = convert_list_to_feature_types(reduced_types)

print(reduced_types)
print(final_types)
