import os
import requests
import json

username = os.getenv("VERIFALIA_USERNAME")
password = os.getenv("VERIFALIA_PASSWORD")

print("🔍 Verifalia API Debug")
print("=" * 60)
print(f"Username: {username}")
print(f"Password: {'*' * 8}")

# Test 1: Submit job
print("\n📤 Submitting verification...")
response = requests.post(
    "https://api.verifalia.com/v2.4/email-validations",
    auth=(username, password),
    json={
        "entries": [{"inputData": "support@verifalia.com"}],
        "quality": "Standard"
    },
    params={"waitTime": "120s"},
    headers={
        "Content-Type": "application/json",
        "Accept": "application/json"
    },
    timeout=130
)

print(f"Status Code: {response.status_code}")
print(f"\n📄 Full Response:")
print(json.dumps(response.json(), indent=2))

# Check structure
data = response.json()
print(f"\n🔍 Response Structure:")
print(f"   Keys: {list(data.keys())}")

if "overview" in data:
    print(f"   Overview: {data['overview']}")

if "progress" in data:
    print(f"   Progress: {data['progress']}")
else:
    print(f"   ⚠️  No 'progress' key found!")

if "entries" in data:
    print(f"   Entries count: {len(data.get('entries', []))}")
    if data.get('entries'):
        print(f"   First entry: {data['entries'][0]}")
else:
    print(f"   ⚠️  No 'entries' key found!")

print("\n" + "=" * 60)
