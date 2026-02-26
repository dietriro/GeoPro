# GeoPro - Geodata Processing

![alt text](resources/geopro_app-overview.svg "GeoPro - Convert places from GMaps to open formats")


This project attempts to provide a complete and user-friendly application for transferring all geographical data from Google Maps to an open source alternative based on OpenStreetMap, specifically CoMaps. The repository includes two different applications, both rely on an initial data extraction from Google Maps. The first application (`gmaps.py`) then scrapes additional information using either a webinterface or API access to Google and saves this in a standardized geojson file. The second application (`osm.py`) reads this data and tries to match each Google Maps location to a place in OpenStreetMap in a semi-automated way. The final result is then a KML file for each original list of places in Google Maps that can then be imported into, e.g., CoMaps or Organic Maps. There is, however, a specific focus and support target towards CoMaps, including FeatureType and Icon information integration, which is used during the CoMaps import. 


## 1. Data preparation

The first step is the data extraction from a Google account. This cannot be automated and has to be performed manually by the user. To retrieve `.csv` files for all of your lists in Google Maps you need to follow these steps:

1. Go to [Google Takeout](https://takeout.google.com)
2. Log into your account
3. Deselect all options
4. Find and select only "Saved" 
5. Wait for the email, download, and unzip takeout data
 
There should be a folder `Saved` in the Takeout archive with a `.csv` file for every list you created in Google Maps. This will be used in the next step to prepare the data for CoMaps.


## 2. Installation

To install the software in this repository, simply download it as a zip file and unpack it or simply clone it via git. Then open a terminal `cd` into the code folder and install the package using pip:

```shell
cd /your/code/folder
pip install .
```

This should not only install the libraries for running everything from the terminal but also `.desktop` files to execute the applications from a graphical desktop environment.


## 3. App 1: Google Maps Information Scraping

To launch the Google Maps information scraping tool, simply execute 

```shell
geopro-gmaps
```

in the terminal or find the graphical application `Geopro-GMaps`. Then proceed with the folling steps in the graphical application interface:

1. Select the source file(s) or folder
2. Select the target file or folder
3. Select a scraping method:
   1. Selenium: uses a chrome webdriver to scrape information from maps.google.com
   2. GMaps API: uses a personalized GMaps API key from your user account ([API key creation instructions](https://expertbeacon.com/how-to-get-a-google-maps-api-key-for-free-and-use-it-right/))
4. (Optional) Enter your API key
5. Select options according to your needs
6. Run the scraping and wait for the result

You can also switch between a dark/light mode in the status bar at the bottom and toggle the visibility of a log for additional information. Basic status information about the process is indicated by the icon and status message on the left of the status bar. 

Once this process is finished you can proceed with the second application to prepare the data for OSM.


## 4. App 2: OSM Place Conversion and Matching

To launch the OSM tool for converting GMaps locations into OSM places, simply execute 

```shell
geopro-osm
```

in the terminal or find the graphical application `Geopro-OSM`. Then proceed with the following steps in the graphical application interface:

1. Select the source file(s) or folder
2. Select the target file or folder
5. Select options according to your needs
6. Select a method for matching GMaps locations to OSM places 
   1. Best: the algorithm always selects the best match, if one was found, otherwise the original location
   2. Threshold: the algorithm only selects the best match, if its score is above the given threshold, otherwise the user is prompted for input
   3. All: the algorithm always prompts the user for input
7. Run the scraping and wait for the result

When you are prompted for input, you will see an OSM map on the top right and potential matches on the lower right side. You can then identify the most suitable match and confirm this (`Confirm selection` button) or choose to go with the original location (`Confirm original location` button). In the middle you can see information about the original location and when double-clicking a location in the table below, you can also view additional information from OSM about this node, way, or relation. 

As in the first app, you can also switch between a dark/light mode in the status bar at the bottom and toggle the visibility of a log for additional information. Basic status information about the process is indicated by the icon and status message on the left of the status bar. 

Once this process is finished you can import the resulting KML file into CoMaps, Organic Maps, or another OpenStreetMap app of your choice that supports KML files. 


## Resources

The animated icons used in the applications in this repository are all based on Icons from Freepik and are available at [Flaticon](www.flaticon.com).
The [Google Maps icon](https://icons8.com/icon/DcygmpZqBEd9/google-maps) is created by [Icons8](https://icons8.com/).
