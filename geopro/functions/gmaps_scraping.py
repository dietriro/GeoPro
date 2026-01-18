from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from datetime import datetime
from urllib.parse import unquote

import pandas as pd
import json
import time
import re
import os
import logging
import requests
import simplekml

from geopro.log import setup_add_logger

log = logging.getLogger("geopro")
setup_add_logger('WDM')


# Config
DATETIME_FORMAT = '%Y-%m-%dT%H:%M:%SZ'
TIMEOUT = 10


class SupportedMethods:
    SELENIUM = "selenium"
    GMAPS_API = "gmaps_api"


def find_element(driver, by, value):
    try:
        return driver.find_element(by, value)
    except NoSuchElementException:
        return None


def extract_address_from_url(url):
    try:
        # Split on '/place/' first
        part = url.split("/place/")[1]
        # Then split on '/data' to get only the address part
        address = part.split("/data")[0]
        # Replace '+' with spaces and decode URL encoding
        address = unquote(address.replace("+", " "))
        return address
    except IndexError:
        return None

def extract_ftid_from_url(url):
    part = url.split('!1s')[-1]
    return part[:37]

def extract_lat_lng(url):
    pattern = r'@(-?\d+\.\d+),(-?\d+\.\d+)'  # Regex pattern to match coordinates
    match = re.search(pattern, url)
    if match:
        latitude = match.group(1)
        longitude = match.group(2)
        return float(latitude), float(longitude)
    return None, None


def convert_geojson_to_kml(geojson_data):
    # Create a new KML object
    kml = simplekml.Kml()

    # Loop through all features
    for feature in geojson_data.get("features", []):
        geom_type = feature["geometry"]["type"]
        coords = feature["geometry"]["coordinates"]
        props = feature.get("properties", {})

        # Build a rich description from properties
        description_lines = []
        for key, value in props.items():
            if isinstance(value, dict):
                # Flatten nested dictionaries (like 'location')
                for sub_key, sub_val in value.items():
                    description_lines.append(f"{sub_key}: {sub_val}")
            else:
                description_lines.append(f"{key}: {value}")
        description_text = "\n".join(description_lines)

        # Add geometry to KML
        if geom_type == "Point":
            kml.newpoint(
                name=props.get("name", ""),
                description=description_text,
                coords=[(coords[0], coords[1])]
            )
        elif geom_type == "LineString":
            kml.newlinestring(
                name=props.get("name", ""),
                description=description_text,
                coords=[(c[0], c[1]) for c in coords]
            )
        elif geom_type == "Polygon":
            kml.newpolygon(
                name=props.get("name", ""),
                description=description_text,
                outerboundaryis=[(c[0], c[1]) for c in coords[0]]
            )

    return kml


def init_webdriver(run_headless):
    # Setup Selenium Chrome driver
    options = webdriver.ChromeOptions()
    options.add_argument('user-data-dir=/home/robin/Code/misc/chrome')
    if run_headless:
        options.add_argument('--headless')
    driver = webdriver.Chrome(options=options, service=Service(ChromeDriverManager().install()))
    return driver


def geocode_address(api_key, place_url, language="de"):
    """
    Get coordinates, place_id, and formatted address from a string address.

    :param address: str, e.g., "Vilsalpsee, Austria"
    :param api_key: str, your Google Maps API key
    :param language: str, optional, language code for returned address
    :return: dict with lat, lng, place_id, formatted_address or None if not found
    """
    params = {
        "key": api_key,
        "language": language,
        "fields": "place_id,geometry,formatted_address"
    }

    if place_url.startswith("https://www.google.com/maps/search/"):
        coordinates = place_url.split('/')[-1]
        # coordinates.reverse()
        # coordinates = ','.join(coordinates)
        params["latlng"] = coordinates
        url = "https://maps.googleapis.com/maps/api/geocode/json"
    elif place_url.startswith('https://www.google.com/maps/place/'):
        params["ftid"] = extract_ftid_from_url(place_url)
        url = "https://maps.googleapis.com/maps/api/place/details/json"
    else:
        log.error(f"Couldn't parse url. Skipping {place_url}")
        return None, None, None, None

    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
    except requests.exceptions.RequestException as e:
        log.error(f"Request failed: {e}")
        return None, None, None, None

    result = None
    if "results" in data.keys():
        if data["results"]:
            result = data["results"][0]
    elif "result" in data.keys():
        result = data["result"]

    if data["status"] != "OK" or result is None:
        log.error(f"Geocoding failed: {data.get('status')}")
        return None, None, None, None

    location = result["geometry"]["location"]
    return location["lat"], location["lng"], result["formatted_address"], result["place_id"]


# Function to extract coordinates from Google Maps URL
def extract_coordinates(url, scraping_method=SupportedMethods.SELENIUM, first_run=False, run_headless=False,
                        language="de", api_key=None):
    if scraping_method == SupportedMethods.SELENIUM:
        log.debug("Using selenium to scrape information")
        driver = init_webdriver(run_headless)

        try:
            # Open the Google Maps URL
            driver.get(url)

            if first_run:
                # Wait for cookie button if it's the first time
                time.sleep(2)  # Wait for the page to load

                # Click the cookie consent button to reject all cookies
                try:
                    cookie_button = driver.find_element(By.XPATH, '//span[text()=\'Alle ablehnen\']')
                    cookie_button.click()
                    time.sleep(2)  # Wait for the popup to close
                except Exception as e:
                    print('Cookie consent button not found or error: ', e)

            # Get new URL
            WebDriverWait(driver, 10).until(
                EC.url_contains('@')
            )
            updated_url = driver.current_url
            log.debug(f'Updated URL: {updated_url}')

            latitude, longitude = extract_lat_lng(updated_url)
            if latitude is None or longitude is None:
                log.warning(f"Could not determine coordinates for: {url}")
            else:
                log.debug(f"Latitude: {latitude}, Longitude: {longitude}")

            address = None
            element_address = find_element(driver, By.XPATH, '//div[contains(@class, \'Io6YTe\')]')
            if element_address is None:
                element_address = find_element(driver, By.XPATH, '//span[contains(@class, \'DkEaL\')]')
                if element_address is None:
                    elements_address = list()
                    elements_address.append(find_element(driver, By.XPATH, "//h1"))
                    elements_address.append(find_element(driver, By.XPATH, "(//h2/span)[1]"))
                    elements_address.append(find_element(driver, By.XPATH, "(//h2/span)[2]"))

                    address = ""
                    for element_address_i in elements_address:
                        if element_address_i is not None:
                            if address != "":
                                address += ", "
                            address += element_address_i.text.strip()

                    if address == "":
                        address = None
                        log.warning(f"Could not find an address for: {url}")

            if element_address is not None and address is None:
                address = str(element_address.text)
            log.debug(address)

            return latitude, longitude, address, None
        except Exception as e:
            print(f'Error extracting coordinates: {e}')
        finally:
            driver.quit()
    elif scraping_method == SupportedMethods.GMAPS_API:
        log.debug("Using google maps API to scrape information")

        if api_key is None:
            log.error(f"A valid api key needs to be provided to scrape information with google maps API.")
            return None, None, None, None




        latitude, longitude, address, place_id = geocode_address(place_url=url,
                                                                 api_key=api_key, language=language)
        if latitude == longitude == address == place_id is None:
            # Try to get updated ftid for place
            driver = init_webdriver(run_headless)
            driver.get(url)
            # Get new URL
            WebDriverWait(driver, 10).until(
                EC.url_contains('@')
            )
            updated_url = driver.current_url
            log.debug(f'Updated URL: {updated_url}')

            latitude, longitude, address, place_id =  geocode_address(place_url=updated_url,
                                                                      api_key=api_key, language=language)

        return latitude, longitude, address, place_id
    else:
        log.error(f"Selected scraping method not supported: {scraping_method}")

    return None, None, None, None

def scrape_from_file(input_file, output_file, overwrite_output=False, update_function=None, run_headless=False,
                     language="de", scraping_method=SupportedMethods.SELENIUM, api_key=None, save_kml=True):

    log.info(f"Beginning scraping for file: {input_file}")

    # Load your CSV file
    df = pd.read_csv(input_file)  # Replace with your CSV file path
    df = df.fillna("")

    features = []

    num_success = 0
    num_failed = 0
    for index, row in df.iterrows():
        url = row['URL']

        if pd.isnull(url) or url.strip() == '':
            log.debug(f'Row {index}: URL is empty or NaN. Skipping...')
            continue  # Skip this row if URL is empty

        name = row.get('Title', 'Unnamed Place')
        note = row.get('Note', '')

        log.info(f"Now scraping: {name}")
        log.debug(f"Note: {note}")

        latitude, longitude, address, place_id = extract_coordinates(url, scraping_method=scraping_method,
                                                                     run_headless=run_headless, language=language,
                                                                     api_key=api_key)

        if (latitude is not None and longitude is not None) or address is not None:
            # Get the current time in UTC
            current_time = datetime.now()

            # Format the time as a string
            datetime_now = current_time.strftime(DATETIME_FORMAT)

            features.append({
                'type': 'Feature',
                'geometry': {
                    'type': 'Point',
                    'coordinates': [longitude, latitude]
                },
                'properties': {
                    'name': name,  # Assuming a name field
                    'date': datetime_now,
                    'description': note,
                    'google_maps_url': url,
                    'google_maps_place_id': place_id,
                    'location': {
                        'address': address,
                        'name': name
                    }
                }
            })
            if latitude is None or longitude is None or address is None:
                num_failed += 1
            else:
                num_success += 1
        else:
            log.error(f'Skipping row {index}: Could not find coordinates or address for the URL {url}')
            num_failed += 1

        update_function(input_file, num_success, num_failed)

    # Create GeoJSON structure
    geojson_data = {
        'type': 'FeatureCollection',
        'features': features
    }

    # Save to GeoJSON file
    output_file_geojson = output_file
    if os.path.exists(output_file_geojson) and overwrite_output or not os.path.exists(output_file_geojson):
        with open(output_file_geojson, 'w') as f:
            json.dump(geojson_data, f)
        log.info(f"GeoJSON file {output_file_geojson} has been created successfully!")
    else:
        log.warning(f"Skipped writing file {output_file_geojson} because it already exists.")

    # Save to KML file
    if save_kml:
        output_file_kml = output_file.replace(".geojson", ".kml")
        if os.path.exists(output_file_kml) and overwrite_output or not os.path.exists(output_file_kml):
            kml = convert_geojson_to_kml(geojson_data)
            kml.save(output_file_kml)
            log.info(f"KML file {output_file_kml} has been created successfully!")
        else:
            log.warning(f"Skipped writing file {output_file_kml} because it already exists.")


