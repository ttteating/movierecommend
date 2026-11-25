import urllib.request
import json

url = "http://127.0.0.1:8000/api/movies/27396"
try:
    with urllib.request.urlopen(url) as response:
        data = json.loads(response.read().decode())
        print("Status: 200 OK")
        print("Movie title:", data.get("moviename", "N/A"))
        print("Categories:", data.get("category_ids", "N/A"))
except Exception as e:
    print("Error:", e)