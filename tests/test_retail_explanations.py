"""Synthetic adversarial explanations; never real generated replies."""
import pytest
from evaluations.two_question_gemini import explanation_checks

EXPECTED=[[["Electronics",260],["Home",150],["Stationery",120]],[["Home",150]]]
BASE="Electronics 260; Home 150; Stationery 120. "


@pytest.mark.parametrize("extra",[
    "Listed highest to lowest.",
    "Sorted from highest to lowest revenue.",
    "Total revenue is 530.",
    "Overall revenue: 530.00.",
    "There are 3 categories.",
    "There are three categories.",
    "Electronics accounts for 49.06% of total revenue.",
    "Home contributes 28.30 percent of total revenue.",
    "Stationery contributes approximately 23% of total revenue.",
    "Electronics ranks first; Home ranks second; Stationery ranks third.",
    "The combined total across all three categories is 530.",
])
def test_correct_derived_and_contextual_claims(extra):
    checks=explanation_checks(0,BASE+extra,EXPECTED)
    assert checks["expected_facts_present"] and checks["numerical_claims_supported"]


@pytest.mark.parametrize("text",[
    "Revenue of 260 for Electronics; revenue of 150 for Home; revenue of 120 for Stationery.",
    "Electronics earned two hundred and sixty; Home earned one hundred and fifty; Stationery earned one hundred and twenty.",
    "From highest to lowest: Electronics 260, Home 150, Stationery 120.",
    "1. Electronics 260\n2. Home 150\n3. Stationery 120",
])
def test_supported_alternative_wording(text):
    checks=explanation_checks(0,text,EXPECTED)
    assert checks["expected_facts_present"] and checks["numerical_claims_supported"]


@pytest.mark.parametrize("extra",[
    "Total revenue is 260.", "Total revenue is 531.",
    "There are 2 categories.", "There are two categories.",
    "Home contributes 49.06% of total revenue.",
    "Home contributes 150% of total revenue.",
    "Electronics contributes 49.9 percent of total revenue.",
    "Home revenue is -150.", "Home revenue is negative 150.",
    "Home revenue is −150.", "Home generated 150 million.",
    "Home generated 120.", "Home ranks first.",
    "Stationery ranks second.", "There were 99 customers.",
    "Home sold 150 units.", "Profit was 150.",
])
def test_wrong_claims_do_not_pass_a_global_number_whitelist(extra):
    checks=explanation_checks(0,BASE+extra,EXPECTED)
    assert not checks["numerical_claims_supported"]


def test_swapped_associations_fail_with_specific_claim():
    checks=explanation_checks(0,"Electronics 150; Home 260; Stationery 120.",EXPECTED)
    assert not checks["expected_facts_present"] and not checks["numerical_claims_supported"]
    assert checks["validation_failures"]


def test_failure_explains_observed_and_expected_total():
    checks=explanation_checks(0,BASE+"Total revenue is 531.",EXPECTED)
    failure=next(f for f in checks["validation_failures"] if f["kind"]=="total")
    assert failure["observed"]==531 and failure["expected"]==530
    assert "531" in failure["claim_excerpt"]


@pytest.mark.parametrize("extra,valid",[
    ("Home accounts for 28.300% of total revenue.",True),
    ("Electronics accounts for 49.056603773585% of total revenue.",True),
    ("Home generated 150 out of 530, accounting for 28.3%.",True),
    ("All three categories account for 100% of revenue.",True),
    ("There are eleven categories.",False),
    ("There are zero categories.",False),
    ("Home has a profit margin of 28.3%.",False),
    ("Home generated 150 out of 260.",False),
    ("All categories account for 150% of revenue.",False),
    ("Confidence is 100%.",False),
])
def test_additional_derived_and_unknown_measure_claims(extra,valid):
    checks=explanation_checks(0,BASE+extra,EXPECTED)
    assert checks["numerical_claims_supported"] is valid


@pytest.mark.parametrize("extra,valid",[
    ("Total revenue across Electronics, Home and Stationery is 530.",True),
    ("Category count: 3.",True),
    ("Home is ranked 2.5.",False),
    ("Home increased revenue by 150.",False),
    ("Home revenue is (150).",False),
])
def test_claim_scope_and_negative_or_unsupported_derivations(extra,valid):
    assert explanation_checks(0,BASE+extra,EXPECTED)["numerical_claims_supported"] is valid
