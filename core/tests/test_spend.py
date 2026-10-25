import json
from types import SimpleNamespace

import anthropic
import httpx2
import pytest

from core.reader import NOTE, CaseFile, ClaudeCaller, Document, ReadFailed, build_request
from core.spend import FALLBACK, PRICES, SpendGuard, actual_usd, worst_case_usd

CASE = CaseFile("ACC-1", "Test Patient", 100_00, (Document("D1", NOTE, "fa_system", None, "household of 4"),))
REQUEST = build_request(CASE)
EMPTY_READING = {"household_size": None, "income_sources": [], "no_income": None, "programs": [], "homeless": None,
                 "conflicts": [], "hidden_instructions": [], "missing": [], "summary": "Nothing here."}
HTTP_REQUEST = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")


def usage(input_tokens=2_000, output_tokens=1_500, iterations=None):
    return SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens, cache_creation_input_tokens=0,
                           cache_read_input_tokens=0, iterations=iterations)


def answer(**tokens):
    return SimpleNamespace(stop_reason="end_turn", model="claude-opus-5-5", usage=usage(**tokens),
                           content=[SimpleNamespace(type="text", text=json.dumps(EMPTY_READING))])


class FakeClient:
    """Looks like anthropic.Anthropic to ClaudeCaller. No network, no money."""

    def __init__(self, respond):
        self.respond, self.calls = respond, 0
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self.create))

    def create(self, **request):
        self.calls += 1
        return self.respond()


@pytest.fixture
def guard(tmp_path):
    return SpendGuard(tmp_path / "spend.db", cap_usd=1.00)


def test_worst_case_covers_all_output_on_opus_and_again_on_the_fallback():
    floor = REQUEST["max_tokens"] * (PRICES["claude-opus-5-5"].output + FALLBACK.output) / 1e6
    assert floor < worst_case_usd(REQUEST) < floor + 0.05


def test_a_call_is_settled_at_what_it_really_cost(guard):
    ClaudeCaller(FakeClient(answer), guard)(REQUEST)
    assert guard.total() == pytest.approx((2_000 * 4.00 + 1_500 * 20.00) / 1e6)


def test_over_the_cap_nothing_is_sent(tmp_path):
    guard = SpendGuard(tmp_path / "spend.db", cap_usd=0.50)  # less than one call's worst case
    client = FakeClient(answer)
    with pytest.raises(ReadFailed, match="spending cap"):
        ClaudeCaller(client, guard)(REQUEST)
    assert client.calls == 0 and guard.total() == 0


def test_the_cap_adds_up_across_runs_and_stops_before_it_is_passed(tmp_path):
    path = tmp_path / "spend.db"
    expensive = lambda: answer(output_tokens=10_000)  # about $0.21 each
    ClaudeCaller(FakeClient(expensive), SpendGuard(path, cap_usd=1.00))(REQUEST)
    later = SpendGuard(path, cap_usd=1.00)  # a new run reads the same ledger
    ClaudeCaller(FakeClient(expensive), later)(REQUEST)
    client = FakeClient(expensive)
    with pytest.raises(ReadFailed, match="spending cap"):
        ClaudeCaller(client, later)(REQUEST)
    assert client.calls == 0
    assert later.total() == pytest.approx(2 * (2_000 * 4.00 + 10_000 * 20.00) / 1e6)
    assert later.total() + worst_case_usd(REQUEST) > later.cap


def test_a_fallback_is_priced_at_the_model_that_ran_it():
    parts = [SimpleNamespace(model="claude-opus-5-5", input_tokens=2_000, output_tokens=500,
                             cache_creation_input_tokens=0, cache_read_input_tokens=0),
             SimpleNamespace(model="claude-opus-4-8", input_tokens=2_000, output_tokens=1_500,
                             cache_creation_input_tokens=0, cache_read_input_tokens=0)]
    cost = actual_usd(usage(iterations=parts), "claude-opus-5-5")
    assert cost == pytest.approx((2_000 * 4 + 500 * 20 + 2_000 * 5 + 1_500 * 25) / 1e6)


def test_an_unknown_model_is_priced_as_the_most_expensive():
    assert actual_usd(usage(input_tokens=1_000_000, output_tokens=0), "claude-made-up") == pytest.approx(10.00)


def test_a_rejected_request_costs_nothing(guard):
    def bad_request():
        raise anthropic.BadRequestError("bad request", response=httpx2.Response(400, request=HTTP_REQUEST), body=None)

    with pytest.raises(ReadFailed, match="400"):
        ClaudeCaller(FakeClient(bad_request), guard)(REQUEST)
    assert guard.total() == 0


def test_a_dropped_connection_keeps_the_worst_case_booked(guard):
    def dropped():
        raise anthropic.APIConnectionError(request=HTTP_REQUEST)

    with pytest.raises(ReadFailed, match="reach"):
        ClaudeCaller(FakeClient(dropped), guard)(REQUEST)
    assert guard.total() == pytest.approx(worst_case_usd(REQUEST))
    assert "held for calls whose cost is unknown" in guard.summary()


def test_a_refusal_is_still_paid_for_and_reported(guard):
    refused = lambda: SimpleNamespace(stop_reason="refusal", model="claude-opus-5-5", usage=usage(output_tokens=0),
                                      content=[])
    with pytest.raises(ReadFailed, match="declined"):
        ClaudeCaller(FakeClient(refused), guard)(REQUEST)
    assert guard.total() == pytest.approx(2_000 * 4.00 / 1e6)


def test_haiku_requests_carry_no_fallback():
    request = build_request(CASE, model="claude-haiku-5-5")
    assert "fallbacks" not in request and "betas" not in request
