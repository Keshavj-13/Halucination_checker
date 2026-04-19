import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.trusted_verifier import verify_with_trusted_knowledge


ABS_TRUE = [
    "A triangle has three sides.",
    "2 + 2 = 4.",
    "All squares have four equal sides.",
    "If something is alive, it is not dead at the same time.",
    "The Earth orbits the Sun.",
    "Water freezes at 0°C at standard atmospheric pressure.",
    "A whole is greater than any of its parts.",
    "No object can be in two completely different places at the same time (classical physics).",
    "All bachelors are unmarried men.",
    "If A = B and B = C, then A = C.",
]

ABS_FALSE = [
    "A square has five sides.",
    "2 + 2 = 5.",
    "All birds are mammals.",
    "A triangle has four sides.",
    "Water boils at 0°C at standard pressure.",
    "A bachelor is a married man.",
    "The Sun revolves around the Earth (in modern astronomy).",
    "Something can be completely black and completely white at the exact same time in the same way.",
    "All humans are reptiles.",
    "No numbers exist.",
]


def test_absolute_truths_never_wrong():
    for claim in ABS_TRUE:
        out = verify_with_trusted_knowledge(claim)
        assert out.status == "Verified", (claim, out)
        assert out.insufficient is False, (claim, out)


def test_absolute_falsehoods_never_wrong():
    for claim in ABS_FALSE:
        out = verify_with_trusted_knowledge(claim)
        assert out.status == "Hallucination", (claim, out)
        assert out.insufficient is False, (claim, out)
