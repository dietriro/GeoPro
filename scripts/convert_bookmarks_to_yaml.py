#!/usr/bin/env python3

import argparse
import re
import yaml
from pathlib import Path
from collections import defaultdict


MAP_ENTRY_RE = re.compile(
    r'\{\s*"([^"]+)"\s*,\s*\{\s*kml::BookmarkIcon::([A-Za-z0-9_]+)\s*,'
)


def parse_cpp_map(cpp_text: str):
    """
    Extract (key, BookmarkIcon) tuples from the C++ map.
    """
    for match in MAP_ENTRY_RE.finditer(cpp_text):
        cpp_key = match.group(1)
        icon = match.group(2)
        yield cpp_key, icon


def decompose_key(cpp_key: str):
    """
    Split the C++ key into at most two levels.
    - Levels are separated by '-'
    - Ignore anything after the second dash
    - If only one level exists, use 'default'
    """
    parts = cpp_key.split("-")

    if len(parts) == 1:
        return parts[0], "default"

    # Only first two levels are kept
    return parts[0], parts[1]


def build_nested_dict(entries):
    """
    Build the nested dictionary structure:
    {
        level1: {
            level2: BookmarkIcon
        }
    }
    """
    result = defaultdict(dict)

    for cpp_key, icon in entries:
        level1, level2 = decompose_key(cpp_key)
        result[level1][level2] = icon

    return result


def main():
    parser = argparse.ArgumentParser(
        description="Convert C++ bookmark map to YAML"
    )
    parser.add_argument(
        "cpp_file",
        type=Path,
        help="Path to the .cpp file containing the map",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("../resources/bookmark_icons.yaml"),
        help="Output YAML file (default: bookmark_icons.yaml)",
    )

    args = parser.parse_args()

    cpp_text = args.cpp_file.read_text(encoding="utf-8")

    entries = list(parse_cpp_map(cpp_text))
    nested = build_nested_dict(entries)

    with args.output.open("w", encoding="utf-8") as f:
        yaml.safe_dump(
            dict(nested),
            f,
            sort_keys=True,
            default_flow_style=False,
        )


if __name__ == "__main__":
    main()
