import copy

def debug_combo_payload(client, page_id, payload):
    tests = []

    tests.append(("FULL", payload))

    p = copy.deepcopy(payload)
    p["definition"]["charts"]["main"]["overrides"] = {}
    tests.append(("NO_SERIES_TYPES", p))

    p = copy.deepcopy(payload)
    p["definition"]["subscriptions"]["main"]["columns"] = \
        p["definition"]["subscriptions"]["main"]["columns"][:2]
    tests.append(("ONLY_BAR", p))

    p = copy.deepcopy(payload)
    p["definition"]["subscriptions"]["main"].pop("dateGrain", None)
    tests.append(("NO_DATE_GRAIN", p))

    p = copy.deepcopy(payload)
    sub = p["definition"]["subscriptions"]["main"]
    sub["columns"][0]["column"] = "attendance_date"
    sub["groupBy"][0]["column"] = "attendance_date"
    tests.append(("RAW_DATE", p))

    print("\n🧪 DOMO COMBO DEBUG START\n")

    for name, test_payload in tests:
        print(f"▶ TEST: {name}")
        try:
            client.create_card(page_id, test_payload)
            print("✅ PASS")
        except Exception as e:
            print("❌ FAIL", e)
