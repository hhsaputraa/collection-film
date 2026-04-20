import os
import requests
from dotenv import load_dotenv

load_dotenv(override=True)

url = os.getenv("SUPABASE_URL", "").strip().rstrip('/')
key = os.getenv("SUPABASE_KEY", "").strip()
user_id = os.getenv("SUPABASE_USER_ID", "").strip()

headers = {
    "apikey": key,
    "Authorization": f"Bearer {key}",
    "Content-Type": "application/json",
    "Prefer": "return=representation"
}

# Test with POST
endpoint = f"{url}/rest/v1/collections?apikey={key}"
payload = {
    "name": "Debug Collection",
    "user_id": user_id
}

print(f"Testing POST to: {endpoint}")
try:
    resp = requests.post(endpoint, json=payload, headers=headers, timeout=10)
    print(f"Status Code: {resp.status_code}")
    print(f"Response: {resp.text}")
except Exception as e:
    print(f"Error: {e}")
