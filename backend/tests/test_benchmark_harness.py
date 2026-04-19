import os
import sys
from collections import Counter

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.benchmark_harness import generate_benchmark


def test_generate_benchmark_has_100_unique_per_category():
    cases = generate_benchmark(per_field_per_category=100, holdout_ratio=0.2, seed=11)

    by_cat = Counter(c.category for c in cases)
    fields = sorted({c.field for c in cases})
    expected_per_category = 100 * len(fields)
    assert by_cat["true"] == expected_per_category
    assert by_cat["false"] == expected_per_category
    assert by_cat["probable"] == expected_per_category

    for category in ("true", "false", "probable"):
        claims = [c.claim.strip().lower() for c in cases if c.category == category]
        assert len(claims) == len(set(claims)), category


def test_generate_benchmark_train_holdout_present_per_category():
    cases = generate_benchmark(per_field_per_category=100, holdout_ratio=0.2, seed=17)
    by_key = Counter((c.category, c.split) for c in cases)

    for category in ("true", "false", "probable"):
        assert by_key[(category, "train")] > 0, category
        assert by_key[(category, "holdout")] > 0, category


def test_generate_benchmark_has_20_plus_fields_with_multiple_statements():
    cases = generate_benchmark(per_field_per_category=100, holdout_ratio=0.2, seed=19)
    fields = sorted({c.field for c in cases})
    assert len(fields) >= 20
    assert "common_knowledge" in fields
    assert "general_knowledge" in fields

    per_field_total = Counter(c.field for c in cases)
    for field, count in per_field_total.items():
        assert count >= 300, (field, count)

    for category in ("true", "false", "probable"):
        per_field_cat = Counter(c.field for c in cases if c.category == category)
        assert all(v == 100 for v in per_field_cat.values()), category
