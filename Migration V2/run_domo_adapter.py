import json
from domo_client import DomoClient
from domo_adapter import DomoAdapter
from dataset_resolver import StaticDatasetResolver
# from domo_auth import get_domo_access_token

# DOMO_CLIENT_ID = "a3ef4f10-2982-4c9e-b6e4-e680ce4dec7b"
# DOMO_CLIENT_SECRET = "a583cf0019a96e256b5c81e2aac730ceab20718e1549486faad5e17f5b582258"

# # --------------------------------------------------
# # Generate Domo OAuth token (REQUIRED)
# # --------------------------------------------------
# access_token = get_domo_access_token(
#     DOMO_CLIENT_ID,
#     DOMO_CLIENT_SECRET
# )

# import jwt

# print("Access token:", access_token)

# decoded = jwt.decode(
#     access_token,
#     options={"verify_signature": False}
# )

# print("\nDecoded token:")
# print(decoded)
# print("\nScopes:")
# print(decoded.get("scope"))


# ---- STEP 1: Load UnifiedBISchema ----
with open("unified_schema.json") as f:
    unified_schema = json.load(f)


# ---- STEP 2: Configure Domo client ----
domo_client = DomoClient(
    base_url="https://gwcteq-partner.domo.com",
    headers = {
        "Content-Type": "application/json;charset=UTF-8",
        "Origin": "https://gwcteq-partner.domo.com",
        "Referer": "https://gwcteq-partner.domo.com",
        "x-requested-with": "XMLHttpRequest",
        "x-csrf-token": "245b4006-1b3e-42c8-89b5-4efb1da46d3f",
        "x-domo-requestcontext": '{"clientToe":"I2PSJ32NTK-QINN8"}',
        "Cookie": "_pubweb_idc=gwcteq-partner_#_standard; SESSION_TOE=I2PSJ32NTK; redirectUrl=%2Fpage%2F1436968545; PLAY_SESSION=c36fa5593ab7be756ccf9fcecc80563927abcc89-isProxied=false; mbox=session#13c3c3650efc4a3b8a2e294c35e02c77#1768882730|PC#13c3c3650efc4a3b8a2e294c35e02c77.41_0#1832125670; _dsidv1=d4324bd5-6050-45c8-a97e-d0ad9833925b; csrf-token=245b4006-1b3e-42c8-89b5-4efb1da46d3f; DA-SID-prod5-gwcteq-partner=eyJjdXN0b21lcklkIjoiZ3djdGVxLXBhcnRuZXIiLCJleHBpcmF0aW9uIjoxNzY4OTE4Mzc5MDAwLCJobWFjU2lnbmF0dXJlIjoiYWEwYmFiOWU2YzA5OTQzZmVmNGYxYmM1ZDJiNzk3YzVjMjYxYjA0ZjY0NzllYjljYTRlMmFhYWM1ZTQ0YWU1MiIsInNpZCI6IjMzNGMyYTIzLWNhOGUtNDhhNS05MzNkLTI3MzY3ZDA3YmIyNCIsInRpbWVzdGFtcCI6MTc2ODg4OTU3OTAwMCwidG9lcyI6IlVOS05PV05TSUQiLCJ1c2VySWQiOiIxNTYxMjIzNDM0In0%3D"
    }
)


# ---- STEP 3: Dataset mapping ----
resolver = StaticDatasetResolver({
    "dataset_1": "2fb72869-5d70-43d9-83e2-932f93a45c7b"
})


# ---- STEP 4: Deploy ----
adapter = DomoAdapter(domo_client, resolver)

adapter.deploy_dashboard(
    unified_schema=unified_schema,
    page_id="13015927758"
)

print("✅ Deployment triggered")
    