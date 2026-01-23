import requests

class DomoClient:
    def __init__(self, base_url, headers):
        self.base_url = base_url.rstrip("/")
        self.headers = headers

    def create_card(self, page_id, payload):
        url = f"{self.base_url}/api/content/v3/cards/kpi?pageId={page_id}"

        print("CREATE CARD")
        print("METHOD: PUT")
        print("URL:", url)

        resp = requests.put(   
            url,
            headers=self.headers,
            json=payload
        )

        print("STATUS:", resp.status_code)
        print("RESPONSE TEXT:", resp.text)

        if resp.status_code not in (200, 201):
            raise RuntimeError(
                f"Domo API error {resp.status_code}: {resp.text}"
            )

        return resp.json()
