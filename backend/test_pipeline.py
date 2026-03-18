import httpx
import asyncio
import json
import time

API_BASE = "http://localhost:8000/api/v1"

async def test_pipeline():
    async with httpx.AsyncClient(timeout=120.0) as client:
        print("1. Creating investigation for Talanta Stadium...")
        res = await client.post(f"{API_BASE}/investigations", json={
            "project_name": "Talanta Stadium",
            "country": "Kenya"
        })
        res.raise_for_status()
        inv_data = res.json()
        inv_id = inv_data["investigation_id"]
        print(f"Created Investigation ID: {inv_id}")

        print("\n2. Enriching investigation context...")
        res = await client.post(f"{API_BASE}/investigations/{inv_id}/enrich")
        res.raise_for_status()
        print("Enrichment complete.")
        
        # Get updated context to see what was found
        res = await client.get(f"{API_BASE}/investigations/{inv_id}/report")
        ctx = res.json().get("context", {})
        print(f"Aliases found: {ctx.get('aliases', [])}")
        print(f"Search terms: {ctx.get('search_terms', [])}")

        print("\n3. Triggering scraping pipeline...")
        res = await client.post(f"{API_BASE}/investigations/{inv_id}/scrape")
        res.raise_for_status()
        print("Scraping triggered. Task runs in background via Celery.")
        
        print("\n4. Polling for results for 60 seconds...")
        for _ in range(12):
            await asyncio.sleep(5)
            res = await client.get(f"{API_BASE}/investigations/{inv_id}/status")
            data = res.json()
            status = data.get("status")
            print(f"Status: {status}")
            if status not in ["DRAFT", "ENRICHING", "SCRAPING"]:
                print("Pipeline moved to next stage:", status)
                print(json.dumps(data.get("stage_statuses", {}), indent=2))
                break

if __name__ == "__main__":
    asyncio.run(test_pipeline())
