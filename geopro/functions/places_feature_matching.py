import csv
import re
from dataclasses import dataclass, field
from typing import List, Tuple, TextIO


TypeStrings = List[str]

@dataclass
class OsmTag:
    key: str
    value: str

    def __init__(self, key, value):
        self.key = key
        self.value = value

    def __eq__(self, other):
        return self.key == other.key and self.value == other.value

# Define a Python representation of a MapCSS rule.
# m_tags: list of (key, value) tuples
# m_mandatoryKeys: list of mandatory keys
# m_forbiddenKeys: list of forbidden keys
@dataclass
class MapcssRule:
    m_tags: List[OsmTag] = field(default_factory=list)
    m_mandatoryKeys: List[str] = field(default_factory=list)
    m_forbiddenKeys: List[str] = field(default_factory=list)

    def matches(self, tags: List[OsmTag]):
        # All required tags must be present
        for tag in self.m_tags:
            if not any(t == tag for t in tags):
                return False

        # Mandatory keys must exist with value != "no"
        for key in self.m_mandatoryKeys:
            if not any(t.key == key and t.value != "no" for t in tags):
                return False

        # Forbidden keys must not exist unless value == "no"
        for key in self.m_forbiddenKeys:
            if not all(t.key != key or t.value == "no" for t in tags):
                return False

        return True


# Type alias for a MapCSS ruleset.
# Each entry is a tuple of type tokens and a MapcssRule.
MapcssRules = List[Tuple[List[str], MapcssRule]]


def parse_mapcss(file_obj: TextIO) -> MapcssRules:
    """
    Parse a MapCSS file and return a list of MapCSS rules.

    Each rule is represented as a tuple of type tokens (list of strings)
    and a MapcssRule object with tags, mandatory keys, and forbidden keys.

    Args:
        file_obj: A file-like object open for reading text.

    Returns:
        List of tuples: [(typeTokens: List[str], rule: MapcssRule), ...]
    """

    rules: MapcssRules = []

    # Helper function to process "short" format rules (3 CSV fields)
    def process_short(type_string: str) -> None:
        type_tokens = type_string.split("|")
        if len(type_tokens) != 2:
            raise ValueError(f"Invalid short type string: {type_string}")

        rule = MapcssRule()
        # The single tag in short format
        rule.m_tags.append(OsmTag(type_tokens[0], type_tokens[1]))
        rules.append((type_tokens, rule))

    # Helper function to process "full" format rules (7 CSV fields)
    def process_full(type_string: str, selectors_string: str) -> None:
        if not type_string or not selectors_string:
            raise ValueError("Empty type string or selectors string")

        type_tokens = type_string.split("|")

        # Each selector is separated by comma
        for selector in selectors_string.split(","):
            selector = selector.strip()

            if selector == "":
                continue
            if not (selector.startswith("[") and selector.endswith("]")):
                raise ValueError(f"Invalid selector format: {selector}")

            rule = MapcssRule()

            # Remove outer brackets and split inner content on brackets
            inner_parts = re.split(r'[\[\]]', selector)
            # re.split produces empty strings for brackets; filter them out
            inner_parts = [part for part in inner_parts if part]

            for kv in inner_parts:
                tag_tokens = kv.split("=")

                # Case 1: Only key present (mandatory or forbidden)
                if len(tag_tokens) == 1:
                    raw_key = tag_tokens[0]
                    forbidden = raw_key.startswith("!")
                    # Strip ! and ? characters
                    key = raw_key.strip("?!")

                    if forbidden:
                        rule.m_forbiddenKeys.append(key)
                    else:
                        rule.m_mandatoryKeys.append(key)

                # Case 2: Key=value pair
                elif len(tag_tokens) == 2:
                    key, value = tag_tokens
                    rule.m_tags.append(OsmTag(key, value))
                else:
                    raise ValueError(f"Invalid tag format in selector: {kv}")

            rules.append((type_tokens, rule))

    # Read CSV lines, preserving empty fields and trimming whitespace
    reader = csv.reader(file_obj, delimiter=";", skipinitialspace=True)

    for fields in reader:
        if not fields:
            continue

        # Skip comments and empty lines
        line_first_field = fields[0].strip()
        if not line_first_field or line_first_field.startswith("#"):
            continue

        # Only lines with 3 or 7 fields are valid
        if len(fields) not in (3, 7):
            raise ValueError(f"Unexpected number of fields ({len(fields)}): {fields}")

        # Short format (3 fields, third field empty)
        if len(fields) == 3 and fields[2] == "":
            process_short(fields[0])

        # Full format (7 fields, third field not 'x')
        if len(fields) == 7 and fields[2] != "x":
            process_full(fields[0], fields[1])

    return rules



def leave_longest_types(matched_types: List[TypeStrings]) -> List[TypeStrings]:
    """
    Replicates C++ LeaveLongestTypes logic exactly.

    If first 2 (or 1 for short types) components are equal,
    only the longest types are kept.
    Equal-length types are preserved.
    """

    def equal_prefix(lhs: TypeStrings, rhs: TypeStrings) -> bool:
        prefix_size = min(len(lhs), len(rhs))
        compare_len = min(2, prefix_size)
        return lhs[:compare_len] == rhs[:compare_len]

    result: List[TypeStrings] = []

    for t in matched_types:
        keep = True
        to_remove = []

        for existing in result:
            if equal_prefix(t, existing):
                if len(t) > len(existing):
                    # New one is better → remove shorter existing
                    to_remove.append(existing)
                elif len(t) < len(existing):
                    # Existing one is better → discard new
                    keep = False
                    break
                else:
                    # Same length → keep both
                    pass

        if keep:
            for r in to_remove:
                result.remove(r)
            result.append(t)

    return result

def convert_list_to_feature_types(feature_list):
    # concatenate all strings from one feature with '-'
    feature_types = ['-'.join(features) for features in feature_list]
    # remove duplicates
    feature_types = list(set(feature_types))

    return feature_types