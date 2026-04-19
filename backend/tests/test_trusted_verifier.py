import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.trusted_verifier import verify_with_trusted_knowledge


def test_trusted_major_source_short_truth_confidence_100():
    out = verify_with_trusted_knowledge("Speed of light is 299,792 km/s")
    assert out.status == "Verified"
    assert out.confidence == 1.0
    assert out.domain in {"physics", "general knowledge"}


def test_trusted_detects_false_ohm_law():
    out = verify_with_trusted_knowledge("Ohm's law states V = I / R")
    assert out.status == "Hallucination"
    assert out.confidence >= 0.98


def test_trusted_insufficient_goes_fallback():
    out = verify_with_trusted_knowledge("This niche startup changed the world last week")
    assert out.insufficient is True
    assert out.status is None


def test_trusted_arithmetic_true_short_circuit():
    out = verify_with_trusted_knowledge("1 + 1 = 2")
    assert out.status == "Verified"
    assert out.insufficient is False
    assert out.reason == "trusted_arithmetic_match"


def test_trusted_arithmetic_false_short_circuit():
    out = verify_with_trusted_knowledge("7 * 8 = 55")
    assert out.status == "Hallucination"
    assert out.insufficient is False
    assert out.reason == "trusted_arithmetic_contradiction"
