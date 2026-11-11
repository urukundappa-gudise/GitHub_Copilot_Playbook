from aimplify_intake.safety.no_facts import classify_no_facts, no_facts_decision


def test_drops_digit_numerals() -> None:
    candidate = {"field_key": "expected_benefits", "value": "Improves productivity by 20 percent"}
    assert no_facts_decision(candidate) == "drop"


def test_drops_percentages() -> None:
    candidate = {"value": "Ninety percent efficiency gain"}
    assert no_facts_decision(candidate) == "drop"


def test_drops_currency_costs() -> None:
    candidate = {"value": "Budget is $5000"}
    assert no_facts_decision(candidate) == "drop"


def test_drops_date_forms() -> None:
    candidate = {"value": "Target date is 2026-11-01"}
    assert no_facts_decision(candidate) == "drop"


def test_drops_word_form_quantities_with_qualifier() -> None:
    candidate = {"value": "over fifteen hours of manual effort"}
    assert no_facts_decision(candidate) == "drop"


def test_drops_entire_nested_candidate_when_any_leaf_has_unverified_quantity() -> None:
    candidate = {"outer": {"safe": "automation uplift", "nested": ["no number", "saves 40 hours"]}}
    assert no_facts_decision(candidate) == "drop"


def test_passes_safe_text_without_unverified_quantity() -> None:
    candidate = {"value": "Improves collaboration and review consistency"}
    assert no_facts_decision(candidate) == "pass"


def test_classifier_returns_distinct_categories_in_fixed_order() -> None:
    candidate = {"nested": ["Costs $500 on 2026-11-01", "ninety percent"]}
    assert classify_no_facts(candidate) == (
        "number",
        "percentage",
        "cost",
        "date",
        "word_quantity",
    )


def test_classifier_keeps_percentage_and_number_categories_distinct() -> None:
    assert classify_no_facts({"value": "Improves efficiency by 20 percent"}) == (
        "number",
        "percentage",
    )


def test_classifier_returns_no_categories_for_safe_text() -> None:
    assert classify_no_facts({"value": "Improves collaboration and review consistency"}) == ()

