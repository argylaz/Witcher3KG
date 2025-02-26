import requests
import json

# API endpoint
url = "https://witcher.fandom.com/api.php"

# Parameters for the API request
params = {
    "action": "query",
    "titles": "Kaer_Morhen",
    "prop": "revisions",
    "rvprop": "content",
    "format": "json"
}

# Send the request
response = requests.get(url, params=params)
data = response.json()

# Extract the page content
pages = data["query"]["pages"]
page_id = list(pages.keys())[0]  # Get the first page ID
content = pages[page_id]["revisions"][0]["*"]

# Create a dictionary to store the content
output_data = {
    "page_id": page_id,
    "title": pages[page_id]["title"],
    "content": content
}

# Save the output to a JSON file
with open("kaer_morhen_content.json", "w", encoding="utf-8") as json_file:
    json.dump(output_data, json_file, ensure_ascii=False, indent=4)

print("Content saved to kaer_morhen_content.json")