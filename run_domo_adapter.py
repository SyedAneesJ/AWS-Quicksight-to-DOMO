# run_domo_adapter.py
import json
import requests
from domo_client import DomoClient
from domo_adapter import DomoAdapter
from dataset_resolver import StaticDatasetResolver

PAGE_ID = "151422060"
BASE_URL = "https://gwcteq-partner.domo.com"

HEADERS = {
    "Content-Type": "application/json;charset=UTF-8",
    "Origin": "https://gwcteq-partner.domo.com",
    "Referer": "https://gwcteq-partner.domo.com",
    "x-requested-with": "XMLHttpRequest",
    "x-csrf-token": "acd77df1-9d45-4d1a-9368-755478219c32",
    "x-domo-requestcontext": '{"clientToe":"4ISK0GAPPD-B4BUV"}',
    "Cookie": "_pubweb_idc=gwcteq-partner_#_standard; _gcl_au=1.1.1490160416.1768980575; _rdt_uuid=1768980575630.749a5ae7-731b-419b-b396-a4a114172841; _ga=GA1.2.77504341.1768980575; _uetvid=f52ca360f69a11f086ac3778fcce0701; signals-sdk-user-id=a030dfce-18b5-44a8-9b20-4ccef987f2a9; eb03b5b0dbaeb744_cfid=b606b64d23ada3a1a034eb16f43f89e01c128f83dcb9a1bc3342dd1c3154a673b1f039c3e29a8fe4a1d9dd724300a06e69542f8ad9ed1b1010659f346f4a27bf; _ga_3RM9SF8PCZ=GS2.1.s1768980575$o1$g1$t1768981263$j60$l0$h0; _ga_ZH4TQCL1RC=GS2.1.s1768980584$o1$g1$t1768981263$j60$l0$h0; SESSION_TOE=4ISK0GAPPD; redirectUrl=%2Fpage%2F1015927758; PLAY_SESSION=c36fa5593ab7be756ccf9fcecc80563927abcc89-isProxied=false; mbox=PC#13c3c3650efc4a3b8a2e294c35e02c77.41_0#1832385554|session#c34cf4e84eb948b9838123bbc02f0bd5#1769142625; _dsidv1=52a46845-abc1-4854-89a0-92269d061991; csrf-token=acd77df1-9d45-4d1a-9368-755478219c32; DA-SID-prod5-gwcteq-partner=eyJjdXN0b21lcklkIjoiZ3djdGVxLXBhcnRuZXIiLCJleHBpcmF0aW9uIjoxNzY5MTY5ODk1MDAwLCJobWFjU2lnbmF0dXJlIjoiNzc3ZWVkZTU0Njg5MjUzZTk3ZmE1N2IxNDIxZjc0MjhiYTE3ZTgxODZjNGE3NzNjMzNiNzc3NzE2YjIxZTNiZCIsInNpZCI6Ijg3MjAzYjVlLWFlMzItNDljMi05YzZjLWI0ZjhmZDgyMDZkYiIsInRpbWVzdGFtcCI6MTc2OTE0MTA5NTAwMCwidG9lcyI6IlVOS05PV05TSUQiLCJ1c2VySWQiOiIxNTYxMjIzNDM0In0%3D"
}

def main():
    print("Deploying dashboard to Domo...")
    
    # Load UnifiedBISchema
    with open("unified_schema.json") as f:
        unified_schema = json.load(f)

    # Configure Domo client
    domo_client = DomoClient(base_url=BASE_URL, headers=HEADERS)

    # Dataset mapping
    resolver = StaticDatasetResolver({
        "dataset_1": "ca04aff7-b666-4dd3-8f9b-c5ae02d57145"
    })

    # Column mapping
    column_mapping = {}

    # Deploy
    adapter = DomoAdapter(domo_client, resolver, column_mapping=column_mapping)
    
    results = adapter.deploy_dashboard(
        unified_schema=unified_schema,
        page_id=PAGE_ID
    )

    # Summary
    success_count = sum(1 for r in results if r["status"] == "SUCCESS")
    failed_count = sum(1 for r in results if r["status"] == "FAILED")
    
    print(f"Deployment complete. Successful: {success_count}, Failed: {failed_count}")
    
    if failed_count > 0:
        print("Failed visuals:")
        for r in results:
            if r["status"] == "FAILED":
                print(f"  - {r['visual_id']}: {r['error']}")

if __name__ == "__main__":
    main()