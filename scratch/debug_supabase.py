import os
import requests
from dotenv import load_dotenv

load_dotenv(override=True)

url = os.getenv("SUPABASE_URL", "").strip().rstrip('/')
key = os.getenv("SUPABASE_KEY", "").strip()

print(f"URL: {url}")
print(f"Key length: {len(key)}")
print(f"Key start: {key[:10]}...")

headers = {
    "apikey": key,
    "Authorization": f"Bearer {key}",
    "Content-Type": "application/json",
    "Prefer": "return=representation"
}

endpoint = f"{url}/rest/v1/collections"
print(f"Endpoint: {endpoint}")

try:
    resp = requests.get(endpoint, headers=headers, timeout=10)
    print(f"Status Code: {resp.status_code}")
    print(f"Response: {resp.text}")
except Exception as e:
    print(f"Error: {e}")
