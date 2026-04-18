import asyncio
import os
import sys
from dotenv import load_dotenv

# Add backend to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from services.claim_extractor import extract_claims
from services.verifier import verify_claim

async def main():
    load_dotenv()
    
    print("--- Multilayer Verification Test ---")
    test_text = "The human brain contains 86 billion neurons. Paris is the capital of France."
    
    claims = await extract_claims(test_text)
    print(f"Extracted Claims: {claims}")
    
    for claim in claims:
        print(f"\nVerifying: {claim}")
        result = await verify_claim(claim["text"])
        print(f"Status: {result.status} (Confidence: {result.confidence})")
        print(f"Evidence: {len(result.evidence)} sources found.")
        
    print("\n--- Data Collection Check ---")
    data_file = os.path.join(os.path.dirname(__file__), "data", "training_data.jsonl")
    if os.path.exists(data_file):
        print("✅ training_data.jsonl created successfully.")
    else:
        print("❌ training_data.jsonl not found.")

if __name__ == "__main__":
    asyncio.run(main())
