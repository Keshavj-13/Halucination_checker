import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models.schemas import Evidence
from services.voters.deterministic_voter import deterministic_voter


def ev(
    snippet: str,
    *,
    domain: str,
    stance: str = "support",
    support: str = "supporting",
    reliability: float = 0.92,
):
    return Evidence(
        title="source",
        snippet=snippet,
        url=f"https://{domain}/ref",
        support=support,
        stance=stance,
        reliability_score=reliability,
        source_domain=domain,
        bias_penalty=0.0,
        sponsorship_flag=False,
    )


def _assert_status(claim: str, expected: str, evidence):
    out = deterministic_voter.vote(claim, evidence)
    support_score = out["metadata"]["support"]
    refute_score = out["metadata"]["refute"]
    detail = {
        "claim": claim,
        "expected": expected,
        "predicted": out["status"],
        "deterministic_label": out["metadata"]["deterministic_label"],
        "support": support_score,
        "refute": refute_score,
        "top_evidence": out["metadata"].get("per_evidence", [])[:3],
    }
    assert out["status"] == expected, detail


def test_core_validation_set_true_false_probable():
    # TRUE
    _assert_status(
        "Earth orbits the Sun",
        "Verified",
        [ev("Earth revolves around the Sun in an annual orbit.", domain="nasa.gov")],
    )
    _assert_status(
        "water is transparent",
        "Verified",
        [ev("Liquid water is transparent to visible light under normal conditions.", domain="britannica.com")],
    )
    _assert_status(
        "speed of light is constant",
        "Verified",
        [ev("In vacuum the speed of light is a universal constant.", domain="nist.gov")],
    )
    _assert_status(
        "water boils at 100 degrees Celsius at standard pressure",
        "Verified",
        [ev("At standard atmospheric pressure, water boils at 100 Celsius.", domain="nist.gov")],
    )
    _assert_status(
        "ice is solid water",
        "Verified",
        [ev("Ice is the solid phase of water.", domain="britannica.com")],
    )

    # FALSE
    _assert_status(
        "Earth is flat",
        "Hallucination",
        [ev("Earth is an oblate spheroid, not flat.", domain="nasa.gov", stance="refute", support="contradicting")],
    )
    _assert_status(
        "water is dry",
        "Hallucination",
        [ev("Water is wet in normal use; it is not dry.", domain="britannica.com", stance="refute", support="contradicting")],
    )
    _assert_status(
        "heat flows from cold to hot",
        "Hallucination",
        [ev("Heat spontaneously flows from hot to cold in thermodynamics.", domain="nist.gov", stance="refute", support="contradicting")],
    )
    _assert_status(
        "vaccines contain chips",
        "Hallucination",
        [ev("Vaccines do not contain tracking chips.", domain="who.int", stance="refute", support="contradicting")],
    )
    _assert_status(
        "AI will replace all developers next month",
        "Hallucination",
        [ev("Near-term claims of replacing all developers are unsupported and speculative.", domain="oecd.org", stance="refute", support="contradicting")],
    )

    # PROBABLE
    _assert_status(
        "AI will replace many jobs over time",
        "Plausible",
        [ev("AI may automate some tasks over time, but impact differs by sector.", domain="worldbank.org", stance="neutral", support="weak", reliability=0.85)],
    )
    _assert_status(
        "coffee is healthy",
        "Plausible",
        [ev("Coffee effects vary with dose and population; evidence is mixed.", domain="nih.gov", stance="neutral", support="weak", reliability=0.86)],
    )
    _assert_status(
        "renewable energy will dominate soon",
        "Plausible",
        [ev("Renewable adoption is increasing, but timelines vary by region and policy.", domain="iea.org", stance="neutral", support="weak", reliability=0.86)],
    )
    _assert_status(
        "social media harms attention in all cases",
        "Plausible",
        [ev("Effects on attention are mixed and context dependent.", domain="nih.gov", stance="neutral", support="weak", reliability=0.86)],
    )


def test_relation_guard_prevents_cross_claim_refute_pollution():
    claim = "water boils at 100 degrees Celsius at standard pressure"
    evidence = [
        ev("At standard pressure, water boils at 100 Celsius.", domain="nist.gov"),
        ev("Heat spontaneously flows from hot to cold.", domain="nist.gov", stance="refute", support="contradicting"),
        ev("Earth is not flat.", domain="nasa.gov", stance="refute", support="contradicting"),
    ]

    out = deterministic_voter.vote(claim, evidence)
    assert out["status"] == "Verified", out
    assert out["metadata"]["support"] > out["metadata"]["refute"], out
