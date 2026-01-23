import requests
from urllib.parse import quote
import json

class DomoClient:
    def __init__(self, base_url, headers):
        self.base_url = base_url.rstrip("/")
        self.headers = headers

    def create_card(self, page_id, payload):
        url = f"{self.base_url}/api/content/v3/cards/kpi?pageId={page_id}"

        print("\n===== DOMO PAYLOAD START =====")
        print(json.dumps(payload, indent=2))
        print("===== DOMO PAYLOAD END =====\n")

        resp = requests.put(
            url,
            headers=self.headers,
            json=payload
        )

        print("STATUS:", resp.status_code)
        print("RESPONSE:", resp.text)

        if resp.status_code not in (200, 201):
            raise RuntimeError(
                f"Domo API error {resp.status_code}: {resp.text}"
            )

        return resp.json()

    
    def create_beast_mode(self, dataset_id: str, name: str, sql: str):
        safe_name = quote(name, safe="")
        url = f"{self.base_url}/api/query/v1/datasources/{dataset_id}/beastmodes/{safe_name}"


        payload = {
            "name": name,
            "sql": sql
        }

        resp = requests.put(
            url,
            headers=self.headers,
            json=payload
        )

        # 409 = already exists (idempotency)
        if resp.status_code == 409:
            print(f"ℹ️ Beast Mode already exists: {name}")
            return None

        if resp.status_code not in (200, 201):
            raise RuntimeError(
                f"Beast Mode creation failed: {resp.status_code} {resp.text}"
            )

        print(f"✅ Beast Mode created: {name}")
        return resp.json()

