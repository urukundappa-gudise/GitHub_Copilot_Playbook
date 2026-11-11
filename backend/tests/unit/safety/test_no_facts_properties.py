from hypothesis import given
from hypothesis import strategies as st

from aimplify_intake.safety.no_facts import classify_no_facts, no_facts_decision


@given(
    amount=st.integers(min_value=0, max_value=999_999),
    currency_spacing=st.sampled_from(["", " ", "\t", "\u2009"]),
    date_separator=st.sampled_from(["-", "/"]),
    year=st.integers(min_value=1900, max_value=2099),
    month=st.integers(min_value=1, max_value=12),
    day=st.integers(min_value=1, max_value=28),
)
def test_nested_normalized_currency_and_date_forms_drop_the_whole_candidate(
    amount: int,
    currency_spacing: str,
    date_separator: str,
    year: int,
    month: int,
    day: int,
) -> None:
    date_value = (
        f"{year:04d}-{month:02d}-{day:02d}"
        if date_separator == "-"
        else f"{month:02d}/{day:02d}/{year:04d}"
    )
    currency_candidate = {
        "field_key": "expected_benefits",
        "value": [{"summary": "Improves team consistency."}, {"evidence": f"Costs ${currency_spacing}{amount:,}."}],
    }
    date_candidate = {
        "field_key": "expected_benefits",
        "value": [{"summary": "Improves team consistency."}, {"evidence": f"Launches {date_value}."}],
    }

    assert no_facts_decision(currency_candidate) == "drop"
    assert no_facts_decision({"nested_claim": currency_candidate}) == "drop"
    assert no_facts_decision(date_candidate) == "drop"
    assert bool(classify_no_facts(currency_candidate)) == (no_facts_decision(currency_candidate) == "drop")
    assert bool(classify_no_facts(date_candidate)) == (no_facts_decision(date_candidate) == "drop")