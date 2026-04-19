import asyncio
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services import verifier as verifier_module


def test_arithmetic_short_circuit_skips_retrieval(monkeypatch):
    async def _boom(*args, **kwargs):
        raise AssertionError("retrieval should not be called for deterministic arithmetic claim")

    monkeypatch.setattr(verifier_module.retrieval_pipeline, "retrieve", _boom)

    claim = asyncio.run(
        verifier_module.verify_claim(
            text="1 + 1 = 2",
            document_id="test-doc",
            start_idx=0,
            end_idx=9,
        )
    )

    assert claim.status == "Verified"
    assert claim.confidence >= 0.98
