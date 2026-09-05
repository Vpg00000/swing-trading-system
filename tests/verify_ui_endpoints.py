import sys
from pathlib import Path
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from web_server import app

def run_verifications():
    client = TestClient(app)

    endpoints = [
        "/api/health",
        "/api/opportunities",
        "/api/priced-in?symbol=RELIANCE.NS",
        "/api/risk",
        "/api/returns",
        "/api/sectors",
        "/api/portfolio",
        "/api/dashboard",
        "/api/grid/stocks?cap_category=ALL&limit=5",
        "/api/research?symbol=RELIANCE.NS",
        "/api/prompts",
        "/api/cyclical",
        "/api/deliveries",
        "/api/filings",
        "/api/flow"
    ]

    print("=== UI API ENDPOINTS VERIFICATION ===")
    all_passed = True
    for ep in endpoints:
        resp = client.get(ep)
        status = resp.status_code
        if status == 200:
            print(f" [PASS] {ep:<45} -> 200 OK ({len(resp.content)} bytes)")
        else:
            print(f" [FAIL] {ep:<45} -> {status} Error: {resp.text}")
            all_passed = False

    if all_passed:
        print("\nALL 15 UI API ENDPOINTS VERIFIED CLEANLY (STATUS 200 OK)!")
    else:
        print("\nSOME ENDPOINTS FAILED!")
        sys.exit(1)

if __name__ == "__main__":
    run_verifications()
