import httpx
import asyncio
import json

API_BASE = "http://localhost:8000/api/v1"

async def test_pipeline():
    async with httpx.AsyncClient(timeout=120.0) as client:
        # 1. Create Investigation
        project_name = "COUNTY ASSEMBLY OF KIRINYAGA OFFICES - KERUGOYA TOWN"
        print(f"1. Creating investigation for {project_name}...")
        res = await client.post(f"{API_BASE}/investigations", json={
            "project_name": project_name,
            "country": "Kenya"
        })
        res.raise_for_status()
        inv_data = res.json()
        inv_id = inv_data["investigation_id"]
        print(f"Created Investigation ID: {inv_id}")

        # 2. Skip enrichment and set context manually
        # Perplexity takes time, we want to just test the scraper string match quickly
        print("\n2. Setting context manually...")
        ctx_payload = {
            "canonical_name": project_name,
            "search_terms": [project_name],
            "aliases": ["COUNTY ASSEMBLY OF KIRINYAGA"],
            "procuring_entity": "COUNTY ASSEMBLY OF KIRINYAGA",
            "country": "Kenya"
        }
        res = await client.patch(f"{API_BASE}/investigations/{inv_id}/context", json=ctx_payload)
        res.raise_for_status()
        print("Context set.")

        # 3. Trigger Scrape
        print("\n3. Triggering scraping pipeline...")
        res = await client.post(f"{API_BASE}/investigations/{inv_id}/scrape")
        res.raise_for_status()
        print("Scraping triggered. Task runs in background via Celery.")
        
        # 4. Poll
        print("\n4. Polling for results for 60 seconds...")
        for _ in range(15):
            await asyncio.sleep(5)
            res = await client.get(f"{API_BASE}/investigations/{inv_id}/status")
            data = res.json()
            status = data.get("status")
            print(f"Status: {status}")
            if status not in ["DRAFT", "ENRICHING", "SCRAPING"]:
                print("\nPipeline moved to next stage:", status)
                print(json.dumps(data.get("stage_statuses", {}), indent=2))
                break

if __name__ == "__main__":
    asyncio.run(test_pipeline())
