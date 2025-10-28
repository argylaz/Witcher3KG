import requests
import json

# URL for Layer 1 of the FeatureServer
url = "https://services6.arcgis.com/22wyIskRdsHsTOJF/ArcGIS/rest/services/The_Magnificent_Map_of_Witcher_3___Wild_Hunt_WFL1/FeatureServer/0/query"

# Query parameters
params = {
    "where": "1=1",               # Get all features
    "outFields": "*",             # Return all fields
    "f": "json",                  # Response format
    "returnGeometry": True        # Include geometry
}

# Send the request
response = requests.get(url, params=params)

# Check if request was successful
if response.status_code == 200:
    data = response.json()
    print(json.dumps(data, indent=2))  # Pretty-print the response
else:
    print(f"Request failed with status code: {response.status_code}")
