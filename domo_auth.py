import requests
from base64 import b64encode


def get_domo_access_token(client_id: str, client_secret: str) -> str:
    """
    Generate OAuth access token using Domo Client Credentials flow
    """

    # Encode client_id:client_secret as Base64
    auth_string = f"{client_id}:{client_secret}"
    encoded_auth = b64encode(auth_string.encode()).decode()

    headers = {
        "Authorization": f"Basic {encoded_auth}",
        "Content-Type": "application/x-www-form-urlencoded"
    }

    data = {
        "grant_type": "client_credentials",
        # minimum scopes required to create cards
        "scope": "dashboard data"
    }

    response = requests.post(
        "https://api.domo.com/oauth/token",
        headers=headers,
        data=data
    )

    if response.status_code != 200:
        raise RuntimeError(
            f"Failed to get Domo token: {response.status_code} {response.text}"
        )

    return response.json()["access_token"]
