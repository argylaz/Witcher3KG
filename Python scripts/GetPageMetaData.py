import requests

# API endpoint
url = "https://witcher.fandom.com/api.php"

# Parameters for the API request
params = {
    "action": "query",
    "titles": "Geralt_of_Rivia",
    "prop": "categories|links",
    "format": "json"
}

# Send the request
response = requests.get(url, params=params)
data = response.json()

# Extract metadata
pages = data["query"]["pages"]
for page_id in list(pages.keys()):
    # page_id = list(pages.keys())[0]  # Get the first page ID
    categories = pages[page_id].get("categories", [])
    links = pages[page_id].get("links", [])

    print("Categories:")
    for category in categories:
        print(category["title"])

    print("\nLinks:")
    for link in links:
        print(link["title"])

# Check if there are more results
# if "continue" in data:
#     params.update(data["continue"])