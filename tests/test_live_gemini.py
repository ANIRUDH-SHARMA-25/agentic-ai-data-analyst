"""Live-runner safeguards and oracles tested without provider calls."""
import pytest
from evaluations.live_gemini import RequestBudget, expected_tables, run_live, table_matches
from backend.agent.analyst import AnalysisError


def test_live_requires_separate_approval():
    with pytest.raises(ValueError,match="approval"):
        run_live()


@pytest.mark.parametrize("maximum,interval",[(17,35),(0,35),(16,0)])
def test_live_limits_are_validated_before_client(maximum,interval):
    with pytest.raises(ValueError):
        run_live(approved=True,max_calls=maximum,interval=interval)


def test_attempt_budget_does_not_replay_requests():
    budget=RequestBudget(maximum=1,interval=0)
    budget.on_chat_model_start({},[])
    with pytest.raises(AnalysisError,match="budget exhausted"):
        budget.on_chat_model_start({},[])
    assert budget.attempts==1


def test_live_oracles_are_independent_and_detect_wrong_tables(retail_frame):
    tables=expected_tables(retail_frame)
    assert tables==[[[530]],[["Electronics",260]],[["Electronics",260],["Home",150],["Stationery",120]],[["Home",150]]]
    assert table_matches(3,[[150]],tables[3])
    assert not table_matches(3,[[120]],tables[3])
    assert not table_matches(0,[[999]],tables[0])
