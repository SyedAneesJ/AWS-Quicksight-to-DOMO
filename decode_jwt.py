import jwt

DOMO_CLIENT_ID = "8519e491-2c27-4b09-a1d7-e3852b33fb75"
DOMO_CLIENT_SECRET = "9db3dc65591db27e015d5634e76716b305a879fb9f93e987e65cac3aa4d7ec60"

# --------------------------------------------------
# Generate Domo OAuth token (REQUIRED)
# --------------------------------------------------
access_token = get_domo_access_token(
    DOMO_CLIENT_ID,
    DOMO_CLIENT_SECRET
)

decoded = jwt.decode(
    access_token,
    options={"verify_signature": False}
)

print("Decoded token:")
print(decoded)
print("\nScopes:")
print(decoded.get("scope"))
