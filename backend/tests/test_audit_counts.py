from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock
import json

from main import app
from models.schemas import Claim

client = TestClient(app)


def _make_claim(text, label, status=None):
    return Claim(
        text=text,
        status=status or ("Verified" if label == "VERIFIED" else "Plausible"),
        confidence=0.5,
        evidence=[],
        start_idx=0,
        end_idx=len(text),
        label=label,
    )


def test_audit_counts_label_aware():
    # Prepare claims with a mix of labels
    claims = [
        _make_claim("A verified fact", "VERIFIED"),
        _make_claim("A refuted fact", "REFUTED"),
        _make_claim("A plausible fact", "PLAUSIBLE"),
        _make_claim("An uncertain fact", "UNCERTAIN"),
        _make_claim("An unverified fact", "UNVERIFIABLE"),
    ]

    body = {"document": "Test document"}

    with patch("routes.audit.verify_claims", new_callable=AsyncMock) as mocked:
        mocked.return_value = claims
        resp = client.post("/audit", json=body)
        assert resp.status_code == 200
        data = resp.json()
        # counts should map labels exactly
        assert data["verified"] == 1
        assert data["hallucinations"] == 1  # REFUTED -> hallucinations
        assert data["plausible"] == 1
        # UNCERTAIN and UNVERIFIABLE should be captured under 'uncertain'
        assert data.get("uncertain", 0) == 2
        assert data["total"] == 5


if __name__ == "__main__":
    print("Run pytest to execute tests")
