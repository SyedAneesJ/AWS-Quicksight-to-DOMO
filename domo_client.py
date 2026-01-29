import requests
import json

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

    def _register_calculated_fields(self, unified_schema: dict):
        dataset_id = self.dataset_resolver.resolve(
            unified_schema["datasets"][0]["id"]
        )

        formulas = []

        for cf in unified_schema.get("calculatedFields", []):
            if cf["calculationType"] != "ROW":
                continue  # v1: only ROW fields here

            formulas.append({
                "name": cf["name"],
                "formula": qs_calc_to_beast_mode({
                    "calculationType": "ROW",
                    "row": cf["normalized"]["row"],
                    "aggregate": None
                })["beast_sql"],
                "dataType": "string",
                "persistedOnDataSource": True,
                "isCalculation": True
            })

        if formulas:
            self.client.register_calculations_via_card_api(
                dataset_id=dataset_id,
                formulas=formulas
            )

    def get_dataset(self, dataset_id: str):
        """
        Fetch dataset schema including calculated fields.
        """
        url = f"{self.base_url}/api/data/v3/datasources/{dataset_id}"

        resp = requests.get(
            url,
            headers=self.headers
        )

        if resp.status_code != 200:
            raise RuntimeError(
                f"Failed to fetch dataset {dataset_id}: "
                f"{resp.status_code} {resp.text}"
            )

        return resp.json()
    
    def update_dataset_formulas(self, dataset_id: str, payload: dict):
        """
        Update dataset-level calculated fields (dsUpdated).
        This is exactly what Domo UI / Sigma does.
        """
        url = f"{self.base_url}/api/content/v3/datasources/{dataset_id}/formulas"

        print("\n===== DOMO DATASET FORMULA PAYLOAD START =====")
        print(json.dumps(payload, indent=2))
        print("===== DOMO DATASET FORMULA PAYLOAD END =====\n")

        resp = requests.put(
            url,
            headers=self.headers,
            json=payload
        )

        print("STATUS:", resp.status_code)
        print("RESPONSE:", resp.text)

        if resp.status_code not in (200, 204):
            raise RuntimeError(
                f"Dataset formula update failed: {resp.status_code} {resp.text}"
            )

        return resp.json() if resp.text else {}
