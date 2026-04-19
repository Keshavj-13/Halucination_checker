import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models.schemas import Evidence
from services.voters.deterministic_voter import deterministic_voter


def ev(snippet: str, *, domain: str = "who.int", stance: str = "support", reliability: float = 0.9, bias: float = 0.0, support: str = "supporting", sponsorship: bool = False):
    return Evidence(
        title="src",
        snippet=snippet,
        url=f"https://{domain}/x",
        support=support,
        stance=stance,
        reliability_score=reliability,
        source_domain=domain,
        bias_penalty=bias,
        sponsorship_flag=sponsorship,
    )


def test_group_f_engineering_fundamentals_verified():
    claims = [
        "Ohm’s law states V = IR",
        "Power equals voltage times current",
        "Increasing resistance reduces current for fixed voltage",
        "Lithium ion batteries degrade with charge cycles",
        "Heat transfer increases with temperature difference",
    ]
    evidence = [
        ev("Ohm's law defines voltage as current multiplied by resistance, V = I*R.", domain="nasa.gov"),
        ev("Electrical power is computed as P = V * I.", domain="mit.edu"),
        ev("For fixed voltage, raising resistance lowers current by Ohm's law.", domain="stanford.edu"),
        ev("Lithium-ion battery capacity declines over many charge-discharge cycles.", domain="nature.com"),
        ev("Heat transfer rate increases with larger temperature difference.", domain="science.org"),
    ]
    for claim in claims:
        out = deterministic_voter.vote(claim, evidence)
        assert out["status"] == "Verified", (claim, out)


def test_group_g_engineering_falsehoods_hallucination():
    claims = [
        "Ohm’s law states V = I / R",
        "Power equals current divided by voltage",
        "Increasing resistance increases current",
        "Batteries improve capacity indefinitely with use",
        "Heat flows from cold to hot naturally",
    ]
    evidence = [
        ev("Ohm's law is V = I*R, not division.", domain="nasa.gov", stance="refute", support="contradicting"),
        ev("Power is product of voltage and current.", domain="mit.edu", stance="refute", support="contradicting"),
        ev("For fixed voltage, resistance and current are inversely related.", domain="stanford.edu", stance="refute", support="contradicting"),
        ev("Battery aging reduces usable capacity over cycle life.", domain="nature.com", stance="refute", support="contradicting"),
        ev("Second law: heat spontaneously flows hot to cold.", domain="science.org", stance="refute", support="contradicting"),
    ]
    for claim in claims:
        out = deterministic_voter.vote(claim, evidence)
        assert out["status"] == "Hallucination", (claim, out)


def test_group_h_complex_engineering_mix():
    good_claims = [
        "GPU parallelism improves matrix multiplication throughput",
        "Reinforcement learning can optimize control systems",
        "Liquid cooling improves thermal efficiency in high load systems",
    ]
    good_evidence = [
        ev("GPU parallel execution increases matrix multiplication throughput for large workloads.", domain="nvidia.com"),
        ev("Reinforcement learning has optimized industrial and robotic control systems.", domain="ieeexplore.ieee.org"),
        ev("Liquid cooling can increase thermal headroom under sustained high load.", domain="tomshardware.com"),
        ev("Benchmarks show higher throughput with GPU matrix kernels.", domain="arxiv.org"),
    ]
    for claim in good_claims:
        out = deterministic_voter.vote(claim, good_evidence)
        assert out["status"] == "Verified", (claim, out)

    hard_claim = "Increasing clock speed always improves performance"
    hard_ev = [
        ev("Higher clock can improve some workloads.", domain="intel.com", stance="support"),
        ev("Performance gains are limited by memory, thermal throttling, and IPC.", domain="amd.com", stance="refute", support="contradicting"),
    ]
    out = deterministic_voter.vote(hard_claim, hard_ev)
    assert out["status"] == "Plausible", out
    assert out["metadata"]["deterministic_label"] in {"Conflicting", "Uncertain"}


def test_group_i_and_j_medical_truth_falsehood():
    truths = [
        "Antibiotics treat bacterial infections",
        "Vaccines stimulate immune response",
        "Insulin regulates blood glucose",
        "Smoking increases risk of lung cancer",
    ]
    falsehoods = [
        "Antibiotics cure viral infections",
        "Vaccines contain tracking microchips",
        "Insulin raises blood sugar",
        "Smoking improves lung health",
    ]

    med_support = [
        ev("Antibiotics are effective against bacterial infections.", domain="who.int"),
        ev("Vaccines train the immune system to recognize pathogens.", domain="cdc.gov"),
        ev("Insulin helps regulate blood glucose levels.", domain="nih.gov"),
        ev("Smoking increases lung cancer risk.", domain="cancer.gov"),
    ]
    med_refute = [
        ev("Antibiotics do not treat viral infections.", domain="who.int", stance="refute", support="contradicting"),
        ev("No vaccine microchip mechanism exists.", domain="cdc.gov", stance="refute", support="contradicting"),
        ev("Insulin lowers blood glucose.", domain="nih.gov", stance="refute", support="contradicting"),
        ev("Smoking harms lungs and overall respiratory function.", domain="who.int", stance="refute", support="contradicting"),
    ]

    for claim in truths:
        out = deterministic_voter.vote(claim, med_support)
        assert out["status"] == "Verified", (claim, out)

    for claim in falsehoods:
        out = deterministic_voter.vote(claim, med_refute)
        assert out["status"] == "Hallucination", (claim, out)


def test_group_k_l_ambiguity_and_adversarial_not_verified():
    ambiguity = [
        "Coffee is good for health",
        "Intermittent fasting improves lifespan",
        "Vitamin supplements are necessary for everyone",
        "Red meat is harmful",
    ]
    mixed = [
        ev("Some studies suggest benefits, but results vary by population.", domain="nih.gov", stance="neutral", reliability=0.8),
        ev("Evidence is mixed and not universally conclusive.", domain="who.int", stance="neutral", reliability=0.85),
        ev("Meta-analyses report heterogeneous outcomes.", domain="nature.com", stance="neutral", reliability=0.82),
    ]
    for claim in ambiguity:
        out = deterministic_voter.vote(claim, mixed)
        assert out["status"] == "Plausible", (claim, out)

    adversarial_claims = [
        "A study funded by oil companies claims plastic is environmentally beneficial",
        "A single paper claims a new drug cures all cancers",
        "A non peer reviewed preprint claims breakthrough energy device",
    ]
    low_quality_support = [
        ev("Sponsored article says plastic is good for environment.", domain="medium.com", reliability=0.35, bias=0.4, sponsorship=True),
        ev("Single unreplicated paper claims cure-all for cancer.", domain="substack.com", reliability=0.33, bias=0.5, sponsorship=True),
        ev("Preprint reports breakthrough device without peer review.", domain="blogspot.com", reliability=0.32, bias=0.45),
    ]
    for claim in adversarial_claims:
        out = deterministic_voter.vote(claim, low_quality_support)
        assert out["status"] != "Verified", (claim, out)


def test_group_m_numeric_consistency_speed_of_light_verified():
    claims = [
        "Speed of light is 299,792 km/s",
        "Speed of light is approximately 3 × 10^8 m/s",
        "Speed of light is 186,000 miles per second",
    ]
    evidence = [
        ev("The speed of light in vacuum is 299792 km/s.", domain="nasa.gov"),
        ev("Equivalent form is about 3 x 10^8 m/s.", domain="physics.org"),
        ev("In imperial units this is around 186000 miles per second.", domain="britannica.com"),
    ]
    for claim in claims:
        out = deterministic_voter.vote(claim, evidence)
        assert out["status"] == "Verified", (claim, out)


def test_group_n_logic_and_consistency():
    true_claims = [
        "If A > B and B > C, then A > C",
        "Division by zero is undefined",
    ]
    false_claim = "Sorting algorithm can run in O(1) time for arbitrary input"

    ev_true = [
        ev("Transitivity holds: if A>B and B>C then A>C.", domain="stanford.edu"),
        ev("Division by zero is undefined in standard arithmetic.", domain="mit.edu"),
    ]
    out1 = deterministic_voter.vote(true_claims[0], ev_true)
    out2 = deterministic_voter.vote(true_claims[1], ev_true)
    out3 = deterministic_voter.vote(false_claim, [ev("Arbitrary input sorting requires more than O(1) time.", domain="mit.edu", stance="refute", support="contradicting")])

    assert out1["status"] == "Verified", out1
    assert out2["status"] == "Verified", out2
    assert out3["status"] == "Hallucination", out3


def test_safety_critical_low_confidence_downgraded_uncertain():
    claim = "In emergency medical settings this drug is always safe for everyone"
    evidence = [
        ev("Some reports suggest benefit in selected groups.", domain="medium.com", reliability=0.35, bias=0.35, stance="neutral"),
    ]
    out = deterministic_voter.vote(claim, evidence)
    assert out["status"] == "Plausible", out
    assert out["metadata"]["deterministic_label"] == "Uncertain", out
    assert out["metadata"].get("warning", "")
