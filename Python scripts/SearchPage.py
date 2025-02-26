import requests

# API endpoint
url = "https://witcher.fandom.com/api.php"

# Parameters for the API request
params = {
    "action": "query",
    "list": "search",
    "srsearch": "Witcher",
    "format": "json"
}

# Send the request
response = requests.get(url, params=params)
data = response.json()

# Extract search results
search_results = data["query"]["search"]
for result in search_results:
    print(f"Title: {result['title']}, Snippet: {result['snippet']}")