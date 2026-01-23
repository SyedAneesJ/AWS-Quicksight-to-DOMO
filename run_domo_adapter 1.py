import json
from domo_client import DomoClient
from domo_adapter import DomoAdapter
from dataset_resolver import StaticDatasetResolver
from domo_auth import get_domo_access_token

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
    headers={
        "Content-Type": "application/json;charset=UTF-8",
        "Origin": "https://gwcteq-partner.domo.com",
        "Referer": "https://gwcteq-partner.domo.com",
        "x-domo-requestcontext": '{"clientToe":"8KP6AF3LJB-H8FG9"}',
        "x-csrf-token": "2ab5ae2e-ea34-4305-8831-769d92bd9551",
        "Cookie": "PLAY_SESSION=c36fa5593ab7be756ccf9fcecc80563927abcc89-isProxied=false; _pubweb_idc=gwcteq-partner_#_standard; redirectUrl=%2Fpage%2F1374335934; SESSION_TOE=8KP6AF3LJB; mbox=PC#314ccd5f89814b1e812a40163fde0bf4.41_0#1832043995|session#6e0e3bfa57ad41928469d0e73c42d2d3#1768801055; _dsidv1=634935b8-cfb8-4842-8f6b-fa85b24ff14c; csrf-token=0014cefc-f547-4e55-9147-91a00042d97e; DA-SID-prod5-gwcteq-partner=eyJjdXN0b21lcklkIjoiZ3djdGVxLXBhcnRuZXIiLCJleHBpcmF0aW9uIjoxNzY4ODI4MjA1MDAwLCJobWFjU2lnbmF0dXJlIjoiZGZkNzY3Y2UyZDE0MGM1N2VkZGM5ODMyMTVmMmRiNDNmZWIwZWIyOTFjZjFmM2NlOTRjODI1ZjdjNzQ4YmViMSIsInNpZCI6IjhjYzBmZmY2LTRjYTgtNDJiOC04OTUzLTg5ZTVjNjQ1ZDA2ZiIsInRpbWVzdGFtcCI6MTc2ODc5OTQwNTAwMCwidG9lcyI6IlVOS05PV05TSUQiLCJ1c2VySWQiOiI4NjUxNDMzMjgifQ%3D%3D",
        "x-requested-with": "XMLHttpRequest"
    }
)


# ---- STEP 3: Dataset mapping ----
resolver = StaticDatasetResolver({
    "dataset_1": "05a52a4e-1e3c-4217-90c6-6843f0666c80"
})


# ---- STEP 4: Deploy ----
adapter = DomoAdapter(domo_client, resolver)

adapter.deploy_dashboard(
    unified_schema=unified_schema,
    page_id="1374335934"
)

print("✅ Deployment triggered")
