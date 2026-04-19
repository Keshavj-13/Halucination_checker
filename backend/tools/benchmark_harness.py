from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import re
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Tuple

from models.schemas import Evidence
from services.config import LOGS_DIR, MODELS_DIR, PROCESSED_DATA_DIR
from services.voters.deterministic_voter import deterministic_voter


BENCHMARK_PATH = PROCESSED_DATA_DIR / "core_benchmark_v1.jsonl"
RUN_LOG_PATH = LOGS_DIR / "benchmark_runs.jsonl"
PROFILE_PATH = MODELS_DIR / "deterministic_tuning_profile.json"

LABEL_TRUE = "Verified"
LABEL_FALSE = "Hallucination"
LABEL_PROBABLE = "Plausible"
ABSOLUTE_CONFIDENCE_THRESHOLD = 0.9
ABSOLUTE_TO_PLAUSIBLE_PENALTY = 3.0
ABSOLUTE_WRONG_LABEL_PENALTY = 1.5
BASE_SEEDS_PER_FIELD_CATEGORY = 10000


@dataclass
class ClaimCase:
    case_id: str
    category: str
    expected_label: str
    claim: str
    evidence: List[Dict[str, object]]
    split: str
    field: str = "general"
    complexity: int = 1


def _hid(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _make_evidence(
    snippet: str,
    *,
    domain: str,
    stance: str = "support",
    support: str = "supporting",
    reliability: float = 0.92,
    bias: float = 0.0,
    sponsorship: bool = False,
) -> Dict[str, object]:
    return {
        "title": "source",
        "snippet": snippet,
        "url": f"https://{domain}/ref",
        "support": support,
        "stance": stance,
        "reliability_score": reliability,
        "source_domain": domain,
        "bias_penalty": bias,
        "sponsorship_flag": sponsorship,
    }


def _to_evidence(items: Sequence[Dict[str, object]]) -> List[Evidence]:
    return [Evidence(**item) for item in items]


def _field_seed_bank() -> Dict[str, Dict[str, List[Tuple[str, str, str]]]]:
    raw = {
        "astronomy": {
            "true": [("Earth orbits the Sun", "Earth revolves around the Sun in a yearly orbit.", "nasa.gov"), ("The Moon orbits Earth", "The Moon is Earth's natural satellite and orbits Earth.", "nasa.gov")],
            "false": [("Earth is flat", "Earth is an oblate spheroid, not flat.", "nasa.gov"), ("The Sun revolves around Earth", "In the heliocentric model, Earth orbits the Sun.", "nasa.gov")],
            "probable": [("A privately funded mission could land humans on Mars in the near future", "Timelines for private Mars missions remain uncertain and policy dependent.", "nasa.gov"), ("Commercial space tourism may become common over time", "Adoption of space tourism depends on cost, safety, and regulation.", "oecd.org")],
        },
        "physics": {
            "true": [("The speed of light in vacuum is constant", "The speed of light in vacuum is a physical constant.", "nist.gov"), ("Heat naturally flows from hot to cold", "Thermodynamics describes spontaneous heat flow from hotter to colder bodies.", "nist.gov")],
            "false": [("Heat flows naturally from cold to hot", "Spontaneous heat flow from cold to hot violates the second law.", "nist.gov"), ("Sound travels faster than light", "Sound speed is far below light speed.", "nist.gov")],
            "probable": [("Room-temperature superconductors may become practical soon", "Practical deployment timelines for room-temperature superconductors are uncertain.", "science.org"), ("Fusion power could become commercially viable in coming decades", "Fusion commercialization remains uncertain and engineering dependent.", "iaea.org")],
        },
        "chemistry": {
            "true": [("Water boils near 100 degrees Celsius at standard pressure", "At standard atmospheric pressure, water boils at about 100 Celsius.", "nist.gov"), ("Pure water freezes near 0 degrees Celsius at standard pressure", "At standard pressure, pure water freezes around 0 Celsius.", "nist.gov")],
            "false": [("Water boils at 50 degrees Celsius at sea level", "At sea level, water boils near 100 Celsius.", "nist.gov"), ("Salt is an element", "Table salt is sodium chloride, a compound.", "britannica.com")],
            "probable": [("A new catalyst may reduce industrial emissions significantly", "Catalyst impact varies by process and scale.", "nature.com"), ("Green hydrogen costs could decline in many regions", "Green hydrogen costs are trending down in some markets but uncertainty remains.", "iea.org")],
        },
        "biology": {
            "true": [("DNA carries genetic information", "DNA stores hereditary genetic information.", "nih.gov"), ("Plants need light for photosynthesis", "Photosynthesis requires light energy.", "nih.gov")],
            "false": [("DNA does not carry genetic information", "DNA is the molecule that carries genetic information.", "nih.gov"), ("Plants photosynthesize without light", "Photosynthesis requires light for energy conversion.", "nih.gov")],
            "probable": [("Microbiome modulation may improve some health outcomes", "Evidence for microbiome interventions is promising but mixed.", "nih.gov"), ("Gene editing could transform treatment of some inherited diseases", "Clinical impact is evolving and context dependent.", "who.int")],
        },
        "medicine": {
            "true": [("Antibiotics treat bacterial infections", "Antibiotics are used for bacterial infections, not viral ones.", "who.int"), ("Vaccines stimulate immune response", "Vaccines activate immune responses against pathogens.", "cdc.gov")],
            "false": [("Antibiotics cure viral infections", "Antibiotics do not treat viral infections.", "who.int"), ("Vaccines contain microchips", "Vaccines do not contain tracking microchips.", "cdc.gov")],
            "probable": [("Coffee may improve health for some people", "Coffee-related outcomes vary with dose and population.", "nih.gov"), ("Intermittent fasting could help some metabolic markers", "Evidence suggests possible benefits, but results vary.", "nih.gov")],
        },
        "history": {
            "true": [("World War II ended in 1945", "World War II ended in 1945.", "britannica.com"), ("The printing press was introduced in Europe in the 15th century", "Movable-type printing expanded in Europe during the 15th century.", "britannica.com")],
            "false": [("World War II ended in 1960", "World War II ended in 1945, not 1960.", "britannica.com"), ("The Roman Empire started in the 20th century", "The Roman Empire predates the 20th century by many centuries.", "britannica.com")],
            "probable": [("A single cause explains the fall of every empire", "Historians typically identify multiple interacting causes.", "britannica.com"), ("Public memory of major wars may shift over generations", "Historical interpretation and memory often evolve over time.", "unesco.org")],
        },
        "geography": {
            "true": [("The Pacific Ocean is the largest ocean", "The Pacific Ocean is the largest ocean basin on Earth.", "noaa.gov"), ("Mount Everest is the highest mountain above sea level", "Everest has the highest elevation above sea level.", "britannica.com")],
            "false": [("The Pacific is the smallest ocean", "The Pacific is the largest, not smallest, ocean.", "noaa.gov"), ("The Nile flows from the Mediterranean to inland Africa", "The Nile flows toward the Mediterranean Sea.", "britannica.com")],
            "probable": [("Sea-level rise may increase coastal flood risk in many regions", "Coastal risk trends vary by location and adaptation policy.", "ipcc.ch"), ("Some cities could face stronger heatwaves over coming decades", "Urban heat trends are likely but locally variable.", "wmo.int")],
        },
        "economics": {
            "true": [("Inflation means a general rise in price levels", "Inflation is a sustained increase in the general price level.", "imf.org"), ("GDP measures total economic output", "GDP measures aggregate production in an economy.", "worldbank.org")],
            "false": [("Inflation always increases purchasing power", "High inflation tends to reduce purchasing power.", "imf.org"), ("GDP counts only exports", "GDP includes consumption, investment, government spending, and net exports.", "worldbank.org")],
            "probable": [("AI adoption may raise productivity in some sectors", "Productivity effects vary by sector, skills, and policy.", "oecd.org"), ("Remote work could reshape urban office demand", "Office demand effects differ by city and industry.", "worldbank.org")],
        },
        "finance": {
            "true": [("Higher risk assets can have higher expected returns", "Risk-return tradeoffs are a core concept in finance.", "investor.gov"), ("Diversification can reduce portfolio-specific risk", "Diversification reduces unsystematic risk.", "sec.gov")],
            "false": [("Diversification guarantees profits", "Diversification reduces some risk but does not guarantee profits.", "sec.gov"), ("Stocks never lose value", "Stock prices can decline.", "investor.gov")],
            "probable": [("Interest rate cuts may increase risk-asset demand", "Market responses to rate cuts vary with macro conditions.", "federalreserve.gov"), ("Crypto regulation could reduce extreme volatility over time", "Regulatory effects on volatility are uncertain.", "bis.org")],
        },
        "sports": {
            "true": [("A soccer match is typically 90 minutes plus stoppage", "Standard association football matches are 90 minutes plus stoppage time.", "fifa.com"), ("A basketball team has five players on court", "In standard basketball, each team has five active players on court.", "fiba.basketball")],
            "false": [("A basketball team uses nine players on court", "Standard basketball uses five players per side on court.", "fiba.basketball"), ("A soccer match has seven innings", "Innings are a baseball concept, not soccer.", "fifa.com")],
            "probable": [("Home advantage may improve win probability", "Home advantage exists in many leagues but varies by competition.", "fifa.com"), ("Performance analytics could improve team outcomes", "Analytics impact depends on implementation quality.", "olympics.com")],
        },
        "computer_science": {
            "true": [("Binary search requires sorted input", "Binary search correctness assumes sorted data.", "python.org"), ("A hash map provides average constant-time lookup", "Hash tables provide average-case near O(1) lookup.", "wikipedia.org")],
            "false": [("Binary search works correctly on arbitrary unsorted lists", "Binary search is not generally correct on unsorted lists.", "python.org"), ("All sorting algorithms run in O(1) for arbitrary input", "General sorting cannot be O(1) on arbitrary input.", "mit.edu")],
            "probable": [("AI coding assistants may improve developer productivity", "Measured productivity gains vary by task and team.", "github.blog"), ("Quantum computing could accelerate some optimization problems", "Benefits are problem-specific and not universal.", "ibm.com")],
        },
        "software_engineering": {
            "true": [("Version control helps track code changes", "Version control systems track and manage source changes.", "git-scm.com"), ("Automated tests can reduce regression risk", "Automated testing helps catch regressions earlier.", "martinfowler.com")],
            "false": [("Unit tests guarantee software has no bugs", "Unit tests improve quality but cannot guarantee zero defects.", "martinfowler.com"), ("One code review always finds every defect", "Code review is useful but not exhaustive.", "atlassian.com")],
            "probable": [("Microservices may improve scalability for some systems", "Microservices benefits depend on architecture and team maturity.", "martinfowler.com"), ("Pair programming could improve code quality in some teams", "Pair programming impact varies by context.", "ieeexplore.ieee.org")],
        },
        "mathematics": {
            "true": [("A triangle has three sides", "By definition, triangles have three sides.", "britannica.com"), ("Division by zero is undefined", "Division by zero is undefined in arithmetic.", "mit.edu")],
            "false": [("Triangles have four sides", "Triangles have three sides, not four.", "britannica.com"), ("Division by zero equals one", "Division by zero is undefined, not equal to one.", "mit.edu")],
            "probable": [("A new proof strategy may simplify some open problems", "Usefulness of new proof strategies is evaluated over time.", "ams.org"), ("Math olympiad training could improve general problem solving", "Transfer effects vary across learners and settings.", "oecd.org")],
        },
        "math": {
            "true": [("1+1=2", "1+1=2", "mathworld.wolfram.com"), ("2*3=6", "2*3=6", "mathworld.wolfram.com")],
            "false": [("1+1=3", "1+1!=3", "mathworld.wolfram.com"), ("2*3=5", "2*3!=5", "mathworld.wolfram.com")],
            "probable": [("x+y=y+x", "x+y=y+x", "mathworld.wolfram.com"), ("x^2+y^2=z^2", "x^2+y^2=z^2", "mathworld.wolfram.com")],
        },
        "literature": {
            "true": [("Shakespeare wrote Hamlet", "William Shakespeare is credited as the author of Hamlet.", "britannica.com"), ("A novel is a form of long prose fiction", "Novels are long-form prose fiction works.", "britannica.com")],
            "false": [("Shakespeare wrote The Odyssey", "The Odyssey is attributed to Homer, not Shakespeare.", "britannica.com"), ("All poems rhyme", "Many poems do not use rhyme.", "poetryfoundation.org")],
            "probable": [("Digital reading may change comprehension for some readers", "Reading medium effects can vary by reader and task.", "apa.org"), ("Audiobooks could increase reading engagement", "Engagement outcomes differ by audience and context.", "unesco.org")],
        },
        "art": {
            "true": [("The Mona Lisa is associated with Leonardo da Vinci", "Leonardo da Vinci is the artist of the Mona Lisa.", "louvre.fr"), ("Perspective is a technique used in visual art", "Linear perspective is a foundational technique in visual art.", "metmuseum.org")],
            "false": [("The Mona Lisa was painted by Vincent van Gogh", "The Mona Lisa is by Leonardo da Vinci, not van Gogh.", "louvre.fr"), ("All art is purely objective and measurable", "Art interpretation includes subjective elements.", "tate.org.uk")],
            "probable": [("AI-generated art may reshape creative workflows", "Impact of AI art tools varies across creators and markets.", "unesco.org"), ("Museum digitization could broaden access to art", "Digital access benefits are real but uneven.", "metmuseum.org")],
        },
        "music": {
            "true": [("A standard piano has 88 keys", "Modern standard pianos typically have 88 keys.", "britannica.com"), ("Tempo is the speed of music", "Tempo describes the speed or pace of a musical piece.", "britannica.com")],
            "false": [("A standard piano has 40 keys", "Standard pianos have far more than 40 keys.", "britannica.com"), ("All music uses the same tempo", "Different pieces can use widely different tempos.", "britannica.com")],
            "probable": [("Streaming platforms may influence music production styles", "Platform incentives can shape style trends, but effects vary.", "ifpi.org"), ("Short-form video could accelerate song discovery", "Discovery effects depend on platform algorithms and audiences.", "ifpi.org")],
        },
        "beauty_cosmetics": {
            "true": [("Sunscreen helps reduce UV skin damage", "Broad-spectrum sunscreen reduces UV exposure and skin damage risk.", "aad.org"), ("Skin types vary across individuals", "Individuals have different skin types and sensitivities.", "aad.org")],
            "false": [("SPF 15 blocks 100 percent of UV rays", "No sunscreen blocks 100 percent of UV rays.", "aad.org"), ("One cosmetic product works equally for every skin type", "Products can perform differently across skin types.", "aad.org")],
            "probable": [("Fermented skincare ingredients may help some users", "Skincare response can vary by ingredient and individual.", "nih.gov"), ("Minimalist routines could improve adherence for many users", "Routine adherence and outcomes vary across people.", "aad.org")],
        },
        "food_nutrition": {
            "true": [("Hydration is important for human health", "Adequate hydration supports normal body function.", "who.int"), ("Protein supports muscle maintenance", "Dietary protein contributes to muscle maintenance.", "nih.gov")],
            "false": [("Humans can survive indefinitely without water", "Humans cannot survive indefinitely without water.", "who.int"), ("Sugar has zero calories", "Sugar provides calories.", "fda.gov")],
            "probable": [("Plant-based diets may improve some health markers", "Benefits depend on dietary quality and individual context.", "who.int"), ("Intermittent fasting could support weight management for some adults", "Weight effects vary by adherence and baseline factors.", "nih.gov")],
        },
        "law": {
            "true": [("Contracts generally require offer and acceptance", "Offer and acceptance are core contract formation elements in many systems.", "law.cornell.edu"), ("Courts interpret statutes", "Courts interpret statutory text in legal disputes.", "supremecourt.gov")],
            "false": [("All contracts are valid without consent", "Consent is generally required for valid contracts.", "law.cornell.edu"), ("Laws never change over time", "Legislation and legal interpretation can change.", "congress.gov")],
            "probable": [("AI tools may increase legal research efficiency", "Efficiency gains vary by workflow and supervision.", "aba.org"), ("Online dispute resolution could expand in civil cases", "Adoption depends on legal frameworks and implementation.", "oecd.org")],
        },
        "linguistics": {
            "true": [("Languages evolve over time", "Languages change over time in vocabulary and grammar.", "britannica.com"), ("Many languages use distinct phonemes", "Phonemic inventories differ among languages.", "cambridge.org")],
            "false": [("Languages never change", "Language change is widely documented.", "britannica.com"), ("Every language has identical grammar", "Grammar structures vary significantly across languages.", "cambridge.org")],
            "probable": [("Machine translation may improve cross-lingual access", "Translation quality is improving but remains context dependent.", "unesco.org"), ("Short-form media could accelerate slang diffusion", "Slang diffusion patterns vary by community and platform.", "oecd.org")],
        },
        "common_knowledge": {
            "true": [("Ice is solid water", "Ice is the solid phase of water.", "britannica.com"), ("The Sun rises in the east", "From Earth, the Sun appears to rise in the east.", "britannica.com")],
            "false": [("Water is dry", "Water is not dry in ordinary usage.", "britannica.com"), ("Humans do not need oxygen", "Humans require oxygen to survive.", "who.int")],
            "probable": [("Early morning routines may improve productivity for some people", "Routine effects differ by individual and context.", "oecd.org"), ("Social habits could influence sleep quality", "Behavioral effects on sleep vary across people.", "nih.gov")],
        },
        "general_knowledge": {
            "true": [("Earth is an oblate spheroid", "Earth is approximately an oblate spheroid.", "nasa.gov"), ("Rain is liquid water falling from clouds", "Rain consists of liquid water droplets falling from clouds.", "noaa.gov")],
            "false": [("The Moon is made of cheese", "The Moon is a rocky natural satellite.", "nasa.gov"), ("Glass is always opaque", "Many forms of glass are transparent.", "britannica.com")],
            "probable": [("Global AI adoption may change many jobs over time", "Labor market impacts are likely but vary by sector.", "oecd.org"), ("Urban density policies could affect housing affordability", "Policy outcomes differ by city and implementation.", "worldbank.org")],
        },
    }

    def _tenfold_rows(rows: List[Tuple[str, str, str]], category: str, field: str) -> List[Tuple[str, str, str]]:
        # 10x more base seed statements before higher-order combinations.
        if field == "math":
            symbol_wrappers = [
                "{}",
                "({})",
                "(({}))",
                "{}",
                "{}",
                "{}",
                "{}",
                "{}",
                "{}",
                "{}",
            ]
            out: List[Tuple[str, str, str]] = []
            for claim, snippet, domain in rows:
                for i, fmt in enumerate(symbol_wrappers, start=1):
                    c = fmt.format(claim.replace(" ", ""))
                    s = fmt.format(snippet.replace(" ", ""))
                    out.append((c, s, domain))
            return out

        lead = {
            "true": [
                "{}",
                "Established fact: {}",
                "Verified baseline: {}",
                "In standard references, {}",
                "Reliable sources confirm {}",
                "Cross-checked claim: {}",
                "Canonical statement: {}",
                "Known true statement: {}",
                "Fundamental fact: {}",
                "Reference-grade claim: {}",
            ],
            "false": [
                "{}",
                "Debunked claim: {}",
                "Known false statement: {}",
                "Contradicted assertion: {}",
                "Rejected claim: {}",
                "Fact-check false: {}",
                "Common misconception: {}",
                "Incorrect baseline: {}",
                "Refuted statement: {}",
                "Invalid claim: {}",
            ],
            "probable": [
                "{}",
                "Plausible but uncertain: {}",
                "Context-dependent claim: {}",
                "Mixed-evidence statement: {}",
                "Debated proposition: {}",
                "Scenario-dependent claim: {}",
                "Tentative forecast: {}",
                "Evidence-evolving claim: {}",
                "Conditionally plausible: {}",
                "Open-outcome statement: {}",
            ],
        }[category]

        evidence_reinforcement = {
            "true": [
                "Independent references report the same underlying fact.",
                "This aligns with standard educational and scientific summaries.",
                "The statement matches widely cited baseline references.",
                "Authoritative sources describe the same relationship.",
                "This is consistent with accepted reference material.",
            ],
            "false": [
                "This is contradicted by established reference material.",
                "Multiple sources classify this as a misconception.",
                "The claim conflicts with standard factual summaries.",
                "Authoritative references explicitly refute this claim.",
                "This statement fails against baseline fact checks.",
            ],
            "probable": [
                "Evidence remains mixed across credible sources.",
                "Outcomes depend on context and assumptions.",
                "Current research does not produce a universal conclusion.",
                "The effect appears conditional across settings.",
                "Published findings show uncertainty and variation.",
            ],
        }[category]

        out: List[Tuple[str, str, str]] = []
        for claim, snippet, domain in rows:
            for i, fmt in enumerate(lead, start=1):
                reinforce = evidence_reinforcement[(i - 1) % len(evidence_reinforcement)]
                out.append((fmt.format(claim), f"{snippet} {reinforce}", domain))
        return out

    def _inflate(
        field: str,
        category: str,
        rows: List[Tuple[str, str, str]],
        target: int = BASE_SEEDS_PER_FIELD_CATEGORY,
    ) -> List[Tuple[str, str, str]]:
        rows = _tenfold_rows(rows, category, field)
        if len(rows) >= target:
            return rows[:target]

        if field == "math":
            # Keep math as symbols only; generate high-volume unique equations.
            variants: List[Tuple[str, str, str]] = []
            seen = set()
            domain = "mathworld.wolfram.com"

            n = 1
            while len(variants) < target:
                a = (n % 997) + 1
                b = ((n * 7) % 991) + 1

                if category == "true":
                    c1 = f"{a}+{b}={a+b}"
                    c2 = f"{a}*{b}={a*b}"
                    c3 = f"({a}+{b})-{b}={a}"
                    cands = [c1, c2, c3]
                elif category == "false":
                    c1 = f"{a}+{b}={a+b+1}"
                    c2 = f"{a}*{b}={a*b+1}"
                    c3 = f"({a}+{b})-{b}={a+1}"
                    cands = [c1, c2, c3]
                else:
                    c1 = f"x+{a}={a}+x"
                    c2 = f"(x+{a})^2=x^2+2*{a}*x+{a*a}"
                    c3 = f"x*({a}+{b})={a}*x+{b}*x"
                    cands = [c1, c2, c3]

                for claim in cands:
                    key = claim
                    if key in seen:
                        continue
                    seen.add(key)
                    variants.append((claim, claim, domain))
                    if len(variants) >= target:
                        return variants
                n += 1

            return variants[:target]

        factual_prefix = {
            "true": [
                "According to reference material,",
                "In standard documentation,",
                "In established summaries,",
                "In mainstream sources,",
                "Across cited references,",
            ],
            "false": [
                "Contrary to evidence,",
                "Despite repeated debunks,",
                "Against established references,",
                "In contradiction with documented facts,",
                "Despite authoritative corrections,",
            ],
            "probable": [
                "Under current evidence,",
                "Given mixed findings,",
                "In conditional scenarios,",
                "Across uncertain projections,",
                "With context-sensitive outcomes,",
            ],
        }[category]

        factual_suffix = {
            "true": [
                "under normal conditions.",
                "as described by trusted references.",
                "in baseline factual framing.",
                "in standard instructional context.",
                "without speculative assumptions.",
            ],
            "false": [
                "and is therefore factually incorrect.",
                "and does not match reliable evidence.",
                "and conflicts with authoritative sources.",
                "and remains a known misconception.",
                "and fails basic factual validation.",
            ],
            "probable": [
                "with outcomes varying by context.",
                "without universal agreement.",
                "pending stronger longitudinal evidence.",
                "with heterogeneous reported effects.",
                "with scenario-dependent conclusions.",
            ],
        }[category]

        evidence_suffix = {
            "true": [
                "Independent sources describe the same relationship.",
                "Reference summaries are consistent on this point.",
                "This matches standard domain explanations.",
                "This is corroborated across mainstream sources.",
                "The statement is stable across educational references.",
            ],
            "false": [
                "Reliable sources directly refute this statement.",
                "This contradicts accepted factual references.",
                "Evidence reviews classify this as incorrect.",
                "This is inconsistent with mainstream documentation.",
                "Fact-checking references reject this claim.",
            ],
            "probable": [
                "Published evidence indicates uncertainty.",
                "Findings vary across populations and settings.",
                "The effect is not universally established.",
                "Research synthesis remains mixed.",
                "Current consensus is conditional rather than absolute.",
            ],
        }[category]

        variants: List[Tuple[str, str, str]] = []
        seen = set()
        for base_claim, base_snippet, domain in rows:
            for p in factual_prefix:
                for s in factual_suffix:
                    for e in evidence_suffix:
                        claim = f"{p} {base_claim} {s}".strip()
                        snippet = f"{base_snippet} {e}".strip()
                        key = (re.sub(r"\s+", " ", claim.lower()), domain)
                        if key in seen:
                            continue
                        seen.add(key)
                        variants.append((claim, snippet, domain))
                        if len(variants) >= target:
                            return variants

        return variants[:target]

    expanded: Dict[str, Dict[str, List[Tuple[str, str, str]]]] = {}
    for field, per_cat in raw.items():
        expanded[field] = {}
        for category, rows in per_cat.items():
            expanded[field][category] = _inflate(field, category, rows)
    return expanded


def _expand_field_candidates(category: str, per_field: int, rnd: random.Random) -> List[Tuple[str, List[Dict[str, object]], str, int]]:
    bank = _field_seed_bank()
    hard_prefixes = {
        "true": [
            "{c}",
            "It is a stable fact that {c}",
            "Independent sources consistently show that {c}",
            "Authoritative references agree that {c}",
            "Cross-checked records confirm that {c}",
            "Even under strict scrutiny, {c}",
            "Empirical evidence supports that {c}",
            "By broad consensus, {c}",
            "It remains true that {c}",
            "Verified data indicate that {c}",
        ],
        "false": [
            "{c}",
            "It is often claimed that {c}",
            "A recurring misinformation line is that {c}",
            "Some narratives insist that {c}",
            "A debunked statement says {c}",
            "Even though it sounds plausible, {c}",
            "A repeated myth is that {c}",
            "A common false claim is that {c}",
            "Contrary to evidence, some say {c}",
            "An incorrect assertion is that {c}",
        ],
        "probable": [
            "{c}",
            "Current evidence suggests that {c}",
            "There is ongoing debate whether {c}",
            "Early signals indicate that {c}",
            "Some studies imply that {c}",
            "It is plausible that {c}",
            "Mixed findings suggest that {c}",
            "A cautious forecast is that {c}",
            "Evidence remains inconclusive but {c}",
            "A conditional view is that {c}",
        ],
    }[category]
    hard_suffixes = {
        "true": [
            "in normal use contexts",
            "under standard conditions",
            "based on established references",
            "without requiring speculative assumptions",
            "across reliable educational sources",
            "in mainstream scientific understanding",
            "according to official documentation",
            "in baseline factual framing",
            "when phrased in plain language",
            "even after adversarial paraphrasing",
        ],
        "false": [
            "despite repeated debunks",
            "even though counterevidence is strong",
            "in contradiction to established facts",
            "without credible verification",
            "despite authoritative corrections",
            "even when checked against official data",
            "despite contradictory measurements",
            "in conflict with standard references",
            "while ignoring clear refutation",
            "despite the known scientific consensus",
        ],
        "probable": [
            "depending on context and assumptions",
            "with substantial uncertainty",
            "across heterogeneous populations",
            "subject to policy and market conditions",
            "with mixed and evolving evidence",
            "without a universal conclusion",
            "with effects varying by region",
            "pending stronger longitudinal data",
            "under scenario-dependent outcomes",
            "without definitive consensus",
        ],
    }[category]

    complexity_variants = [
        (1, "", "", ""),
        (2, "For baseline validation,", "", ""),
        (3, "In plain language,", "when interpreted literally", ""),
        (4, "Under deterministic review,", "after basic entity and relation checks", ""),
        (5, "Across independent references,", "with wording variation and paraphrase noise", ""),
        (6, "In adversarial paraphrasing conditions,", "after filtering rhetoric and framing", "without changing semantic meaning"),
        (7, "After normalization of terms and aliases,", "with potential lexical distractions present", "under strict stance interpretation"),
        (8, "When tested against contradictory narrative framing,", "while preserving formal claim semantics", "with robustness constraints enabled"),
        (9, "In high-noise benchmark settings,", "under competing cues and confidence pressure", "with deterministic safety-first scoring"),
        (10, "In maximum-complexity validation mode,", "across layered paraphrase and distractor structures", "with strict contradiction dominance and confidence penalties"),
    ]

    out: List[Tuple[str, List[Dict[str, object]], str, int]] = []
    for field, field_rows in bank.items():
        seeds = field_rows[category]
        seen = set()
        field_out: List[Tuple[str, List[Dict[str, object]], str, int]] = []
        attempts = 0
        max_attempts = max(50_000, per_field * 80)

        math_symbol_prefixes = ["", "(", "((", "", "", "", "", "", "", ""]
        math_symbol_suffixes = ["", ")", "))", "", "", "", "", "", "", ""]

        while len(field_out) < per_field and attempts < max_attempts:
            attempts += 1
            base_claim, snippet, domain = seeds[rnd.randrange(len(seeds))]
            if field == "math":
                pi = rnd.randrange(len(math_symbol_prefixes))
                si = rnd.randrange(len(math_symbol_suffixes))
                complexity = ((pi + si) % 10) + 1
                claim = f"{math_symbol_prefixes[pi]}{base_claim.replace(' ', '')}{math_symbol_suffixes[si]}"
            else:
                pref = hard_prefixes[rnd.randrange(len(hard_prefixes))]
                suff = hard_suffixes[rnd.randrange(len(hard_suffixes))]
                complexity, lead, mid, tail = complexity_variants[rnd.randrange(len(complexity_variants))]
                core = f"{pref.format(c=base_claim)} {suff}".strip()
                claim = " ".join(part for part in [lead, core, mid, tail] if part).strip()
            key = re.sub(r"\s+", " ", claim.lower())
            if key in seen:
                continue
            seen.add(key)

            if category == "true":
                evidence = [
                    _make_evidence(snippet, domain=domain),
                    _make_evidence("Independent references align with this statement." if field != "math" else snippet, domain="britannica.com" if field != "math" else domain, reliability=0.84),
                ]
            elif category == "false":
                evidence = [
                    _make_evidence(snippet, domain=domain, stance="refute", support="contradicting"),
                    _make_evidence("This claim is contradicted by reliable references." if field != "math" else snippet, domain="britannica.com" if field != "math" else domain, stance="refute", support="contradicting", reliability=0.84),
                ]
            else:
                evidence = [
                    _make_evidence(snippet, domain=domain, stance="neutral", support="weak", reliability=0.84),
                    _make_evidence("Evidence is mixed and context-dependent." if field != "math" else snippet, domain="oecd.org" if field != "math" else domain, stance="neutral", support="weak", reliability=0.82),
                ]

            field_out.append((claim, evidence, field, complexity))

        if len(field_out) < per_field:
            raise ValueError(f"Could not generate enough unique claims for field={field} category={category}. generated={len(field_out)} needed={per_field}")

        out.extend(field_out)
    return out


def _dedupe_cases(items: Iterable[Tuple[str, List[Dict[str, object]], str, int]]) -> List[Tuple[str, List[Dict[str, object]], str, int]]:
    out = []
    seen = set()
    for claim, ev, field, complexity in items:
        c = re.sub(r"\s+", " ", claim.strip().lower())
        if c in seen:
            continue
        seen.add(c)
        out.append((claim.strip(), ev, field, complexity))
    return out


def generate_benchmark(per_field_per_category: int = 1000, holdout_ratio: float = 0.2, seed: int = 23) -> List[ClaimCase]:
    rnd = random.Random(seed)
    true_items = _expand_field_candidates("true", per_field_per_category, rnd)
    false_items = _expand_field_candidates("false", per_field_per_category, rnd)
    probable_items = _expand_field_candidates("probable", per_field_per_category, rnd)

    all_cases: List[ClaimCase] = []

    def _split_index(total: int) -> int:
        return max(1, int(round(total * (1.0 - holdout_ratio))))

    def _add(items: List[Tuple[str, List[Dict[str, object]], str, int]], category: str, expected: str):
        split_at = _split_index(len(items))
        for i, (claim, ev, field, complexity) in enumerate(items):
            split = "train" if i < split_at else "holdout"
            all_cases.append(
                ClaimCase(
                    case_id=f"{category}-{_hid(claim)}",
                    category=category,
                    expected_label=expected,
                    claim=claim,
                    evidence=ev,
                    split=split,
                    field=field,
                    complexity=complexity,
                )
            )

    _add(true_items, "true", LABEL_TRUE)
    _add(false_items, "false", LABEL_FALSE)
    _add(probable_items, "probable", LABEL_PROBABLE)

    return all_cases


def save_benchmark(cases: Sequence[ClaimCase], path: Path = BENCHMARK_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for case in cases:
            f.write(json.dumps(asdict(case), ensure_ascii=False) + "\n")


def load_benchmark(path: Path = BENCHMARK_PATH) -> List[ClaimCase]:
    with path.open("r", encoding="utf-8") as f:
        out: List[ClaimCase] = []
        for line in f:
            if not line.strip():
                continue
            row = json.loads(line)
            row.setdefault("field", "general")
            row.setdefault("complexity", 1)
            out.append(ClaimCase(**row))
        return out


def _classify_failure(case: ClaimCase, predicted: str, metadata: Dict[str, object]) -> str:
    if predicted == case.expected_label:
        return "PASS"

    support = float(metadata.get("support", 0.0) or 0.0)
    refute = float(metadata.get("refute", 0.0) or 0.0)
    per_evidence = metadata.get("per_evidence", []) or []
    rel_scores = [float(x.get("relation_match", 0.0) or 0.0) for x in per_evidence if isinstance(x, dict)]
    num_scores = [float(x.get("numeric_match", 0.0) or 0.0) for x in per_evidence if isinstance(x, dict)]

    avg_rel = sum(rel_scores) / max(1, len(rel_scores))
    avg_num = sum(num_scores) / max(1, len(num_scores))
    has_number = bool(re.search(r"\d", case.claim))

    if case.expected_label == LABEL_TRUE:
        if support < 0.15 and refute < 0.15:
            return "RETRIEVAL_FAILURE"
        if avg_rel < 0.35:
            return "RELATION_FAILURE"
        if has_number and avg_num < 0.5:
            return "NUMERIC_FAILURE"
        return "OVER_STRICT"

    if case.expected_label == LABEL_FALSE:
        if refute < 0.15:
            return "STANCE_FAILURE"
        if avg_rel < 0.35:
            return "RELATION_FAILURE"
        if has_number and avg_num < 0.5:
            return "NUMERIC_FAILURE"
        return "OVER_SOFT"

    # expected probable
    if predicted in {LABEL_TRUE, LABEL_FALSE}:
        return "OVER_SOFT"
    return "RETRIEVAL_FAILURE"


def _set_tuning_env(params: Dict[str, float]) -> None:
    for k, v in params.items():
        os.environ[k] = str(v)


def _predict(case: ClaimCase) -> Tuple[str, Dict[str, object], float]:
    out = deterministic_voter.vote(case.claim, _to_evidence(case.evidence))
    return out["status"], out.get("metadata", {}), float(out.get("confidence", 0.0) or 0.0)


def evaluate(
    cases: Sequence[ClaimCase],
    *,
    split: str,
    blind: bool = True,
    run_id: str = "manual",
) -> Dict[str, object]:
    filtered = [c for c in cases if c.split == split]
    by_category_total = Counter(c.category for c in filtered)
    by_field_total = Counter(c.field for c in filtered)
    by_complexity_total = Counter(c.complexity for c in filtered)

    correct = 0
    confusion = Counter()
    category_correct = Counter()
    field_correct = Counter()
    complexity_correct = Counter()
    failure_types = Counter()
    absolute_case_count = 0
    low_confidence_absolute_count = 0
    uncertainty_penalty = 0.0
    absolute_label_penalty = 0.0
    abs_conf_sum = 0.0

    for case in filtered:
        pred, metadata, confidence = _predict(case)
        confusion[(case.expected_label, pred)] += 1

        if case.expected_label in {LABEL_TRUE, LABEL_FALSE}:
            absolute_case_count += 1
            abs_conf_sum += confidence
            if confidence < ABSOLUTE_CONFIDENCE_THRESHOLD:
                low_confidence_absolute_count += 1
                uncertainty_penalty += (ABSOLUTE_CONFIDENCE_THRESHOLD - confidence)
            if pred == LABEL_PROBABLE:
                absolute_label_penalty += ABSOLUTE_TO_PLAUSIBLE_PENALTY
            elif pred != case.expected_label:
                absolute_label_penalty += ABSOLUTE_WRONG_LABEL_PENALTY

        if pred == case.expected_label:
            correct += 1
            category_correct[case.category] += 1
            field_correct[case.field] += 1
            complexity_correct[case.complexity] += 1
            continue
        ft = _classify_failure(case, pred, metadata)
        failure_types[ft] += 1

    category_acc = {
        cat: round(category_correct[cat] / max(1, total), 4)
        for cat, total in sorted(by_category_total.items())
    }
    field_acc = {
        fld: round(field_correct[fld] / max(1, total), 4)
        for fld, total in sorted(by_field_total.items())
    }
    complexity_acc = {
        int(level): round(complexity_correct[level] / max(1, total), 4)
        for level, total in sorted(by_complexity_total.items())
    }
    macro_acc = round(sum(category_acc.values()) / max(1, len(category_acc)), 4)
    overall_acc = round(correct / max(1, len(filtered)), 4)
    avg_absolute_confidence = round(abs_conf_sum / max(1, absolute_case_count), 4)
    adjusted_overall = round(max(0.0, (correct - uncertainty_penalty - absolute_label_penalty) / max(1, len(filtered))), 4)

    report = {
        "run_id": run_id,
        "split": split,
        "blind": blind,
        "count": len(filtered),
        "overall_accuracy": overall_acc,
        "overall_adjusted_for_uncertainty": adjusted_overall,
        "macro_accuracy": macro_acc,
        "category_accuracy": category_acc,
        "field_count": len(by_field_total),
        "field_accuracy": field_acc,
        "complexity_accuracy": complexity_acc,
        "absolute_case_count": absolute_case_count,
        "absolute_avg_confidence": avg_absolute_confidence,
        "absolute_low_confidence_count": low_confidence_absolute_count,
        "absolute_uncertainty_penalty": round(uncertainty_penalty, 4),
        "absolute_label_penalty": round(absolute_label_penalty, 4),
        "failure_types": dict(sorted(failure_types.items())),
        "confusion": {
            f"{e}->{p}": n
            for (e, p), n in sorted(confusion.items(), key=lambda x: (x[0][0], x[0][1]))
        },
    }

    RUN_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with RUN_LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(report, ensure_ascii=False) + "\n")

    if blind:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(json.dumps(report, indent=2, ensure_ascii=False))

    return report


def _dominant_failure(failure_types: Dict[str, int]) -> str:
    if not failure_types:
        return "PASS"
    return max(failure_types.items(), key=lambda x: x[1])[0]


def _propose_params(current: Dict[str, float], dominant_failure: str) -> Dict[str, float]:
    p = dict(current)

    if dominant_failure in {"OVER_STRICT", "RETRIEVAL_FAILURE"}:
        p["DET_VERIFY_RATIO"] = max(1.2, p["DET_VERIFY_RATIO"] - 0.1)
        p["DET_VERIFIED_SUPPORT_FLOOR"] = max(0.55, p["DET_VERIFIED_SUPPORT_FLOOR"] - 0.05)
    elif dominant_failure in {"OVER_SOFT", "STANCE_FAILURE"}:
        p["DET_HALLUCINATION_RATIO"] = max(1.2, p["DET_HALLUCINATION_RATIO"] - 0.1)
        p["DET_STRONG_REFUTE_REL_THRESHOLD"] = max(0.5, p["DET_STRONG_REFUTE_REL_THRESHOLD"] - 0.03)
        p["DET_STRONG_REFUTE_RELIABILITY_THRESHOLD"] = max(0.55, p["DET_STRONG_REFUTE_RELIABILITY_THRESHOLD"] - 0.03)
    elif dominant_failure == "RELATION_FAILURE":
        p["DET_CONTRADICTION_REL_THRESHOLD"] = max(0.45, p["DET_CONTRADICTION_REL_THRESHOLD"] - 0.05)
    elif dominant_failure == "NUMERIC_FAILURE":
        p["DET_STRONG_EVIDENCE_THRESHOLD"] = max(0.04, p["DET_STRONG_EVIDENCE_THRESHOLD"] - 0.01)

    return p


def _score_report(report: Dict[str, object]) -> Tuple[float, float, float, float]:
    category_acc = report.get("category_accuracy", {}) or {}
    failure_types = report.get("failure_types", {}) or {}
    fail_count = float(sum(float(v) for v in failure_types.values()))
    uncertainty_penalty = float(report.get("absolute_uncertainty_penalty", 0.0) or 0.0)
    label_penalty = float(report.get("absolute_label_penalty", 0.0) or 0.0)
    adjusted = float(report.get("overall_adjusted_for_uncertainty", 0.0) or 0.0)
    return (
        adjusted,
        float(report.get("macro_accuracy", 0.0)),
        float(report.get("overall_accuracy", 0.0)),
        float(category_acc.get("false", 0.0)),
        -(fail_count + uncertainty_penalty + label_penalty),
    )


def _neighbor_params(current: Dict[str, float], dominant_failure: str) -> List[Dict[str, float]]:
    seeds = [_propose_params(current, dominant_failure)]
    neighbors: List[Dict[str, float]] = []

    for p in seeds:
        neighbors.append(dict(p))

        x = dict(p)
        x["DET_VERIFY_RATIO"] = max(1.1, x["DET_VERIFY_RATIO"] - 0.15)
        x["DET_VERIFIED_SUPPORT_FLOOR"] = max(0.5, x["DET_VERIFIED_SUPPORT_FLOOR"] - 0.05)
        neighbors.append(x)

        y = dict(p)
        y["DET_HALLUCINATION_RATIO"] = max(1.1, y["DET_HALLUCINATION_RATIO"] - 0.15)
        y["DET_STRONG_REFUTE_REL_THRESHOLD"] = max(0.45, y["DET_STRONG_REFUTE_REL_THRESHOLD"] - 0.05)
        y["DET_STRONG_REFUTE_RELIABILITY_THRESHOLD"] = max(0.5, y["DET_STRONG_REFUTE_RELIABILITY_THRESHOLD"] - 0.05)
        neighbors.append(y)

        z = dict(p)
        z["DET_STRONG_EVIDENCE_THRESHOLD"] = max(0.03, z["DET_STRONG_EVIDENCE_THRESHOLD"] - 0.01)
        neighbors.append(z)

    unique = []
    seen = set()
    for n in neighbors:
        key = tuple(sorted((k, round(v, 6)) for k, v in n.items()))
        if key in seen:
            continue
        seen.add(key)
        unique.append(n)
    return unique


def autotune(cases: Sequence[ClaimCase], iterations: int = 8) -> Dict[str, object]:
    params: Dict[str, float] = {
        "DET_VERIFY_RATIO": 2.0,
        "DET_HALLUCINATION_RATIO": 2.0,
        "DET_STRONG_REFUTE_REL_THRESHOLD": 0.7,
        "DET_STRONG_REFUTE_RELIABILITY_THRESHOLD": 0.75,
        "DET_CONTRADICTION_REL_THRESHOLD": 0.65,
        "DET_CONTRADICTION_RELIABILITY_THRESHOLD": 0.65,
        "DET_STRONG_EVIDENCE_THRESHOLD": 0.08,
        "DET_VERIFIED_SUPPORT_FLOOR": 0.8,
    }

    best_params = dict(params)
    _set_tuning_env(best_params)
    best = evaluate(cases, split="train", blind=True, run_id="autotune-baseline")
    best_score = _score_report(best)

    for i in range(1, iterations + 1):
        dom = _dominant_failure(best.get("failure_types", {}))
        if dom == "PASS":
            break

        improved = False
        for j, proposal in enumerate(_neighbor_params(best_params, dom), start=1):
            _set_tuning_env(proposal)
            trial = evaluate(cases, split="train", blind=True, run_id=f"autotune-iter-{i}-cand-{j}")
            trial_score = _score_report(trial)
            if trial_score > best_score:
                best = trial
                best_score = trial_score
                best_params = proposal
                improved = True

        if not improved:
            _set_tuning_env(best_params)

    PROFILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with PROFILE_PATH.open("w", encoding="utf-8") as f:
        json.dump(best_params, f, indent=2)

    _set_tuning_env(best_params)
    holdout = evaluate(cases, split="holdout", blind=True, run_id="autotune-holdout")

    out = {
        "best_train": best,
        "holdout": holdout,
        "best_params": best_params,
        "profile_path": str(PROFILE_PATH),
    }
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return out


def _load_or_generate(per_field_per_category: int, holdout_ratio: float, seed: int, force: bool) -> List[ClaimCase]:
    if force or not BENCHMARK_PATH.exists():
        cases = generate_benchmark(per_field_per_category=per_field_per_category, holdout_ratio=holdout_ratio, seed=seed)
        save_benchmark(cases, BENCHMARK_PATH)
        return cases
    return load_benchmark(BENCHMARK_PATH)


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Blind benchmark and autotuning harness for hallucination classification")
    sub = p.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("generate", help="Generate benchmark dataset")
    g.add_argument("--per-field-per-category", type=int, default=10000)
    g.add_argument("--per-category", type=int, default=None, help="Deprecated alias; use --per-field-per-category")
    g.add_argument("--holdout-ratio", type=float, default=0.2)
    g.add_argument("--seed", type=int, default=23)
    g.add_argument("--force", action="store_true")

    e = sub.add_parser("evaluate", help="Evaluate benchmark split with blind aggregate report")
    e.add_argument("--split", choices=["train", "holdout"], default="holdout")
    e.add_argument("--blind", action="store_true", default=True)

    a = sub.add_parser("autotune", help="Run blind iterative tuning on train split, report holdout summary")
    a.add_argument("--iterations", type=int, default=8)

    return p


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    if args.cmd == "generate":
        per_field_per_category = args.per_field_per_category if args.per_category is None else args.per_category
        cases = _load_or_generate(per_field_per_category, args.holdout_ratio, args.seed, args.force)
        counts = Counter((c.category, c.split) for c in cases)
        field_counts = Counter(c.field for c in cases)
        report = {
            "path": str(BENCHMARK_PATH),
            "total": len(cases),
            "counts": {f"{k[0]}:{k[1]}": v for k, v in sorted(counts.items())},
            "field_count": len(field_counts),
            "base_seeds_per_field_per_category": BASE_SEEDS_PER_FIELD_CATEGORY,
            "per_field_per_category": per_field_per_category,
        }
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return

    cases = _load_or_generate(10000, 0.2, 23, False)

    if args.cmd == "evaluate":
        evaluate(cases, split=args.split, blind=args.blind, run_id="manual-eval")
        return

    if args.cmd == "autotune":
        autotune(cases, iterations=args.iterations)
        return


if __name__ == "__main__":
    main()
