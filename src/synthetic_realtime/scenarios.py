"""Deterministic synthetic scenario generation.

Implements the full named scenario set: ``normal_baseline`` (ordinary
traffic, no anomaly), ``new_device_burst``, ``address_fan_out``,
``vpn_geography_mismatch``, ``retry_storm``, ``unusual_amount``,
``merchant_deviation``, ``duplicate``, and ``out_of_order``. Each of the
eight non-baseline scenarios is built to reliably trip its corresponding
feature-family signal (see ``features/*.py``) when replayed through a
``SyntheticEventStore`` in generation order, and several import their
family's illustrative threshold directly so the scenario always stays
correctly sized if that threshold changes.

Every generator here is a pure function of (seed, start, event_count): the
same arguments always produce events that compare equal, and entity tokens
are derived from the seed alone, independent of the start time, via
``derive_seed``/``new_rng`` from ``clock.py`` (never the global ``random``
module). This module must never import the historical XGBoost model, SHAP,
thresholds, metrics, or Bundle v3 code.

``normal_baseline`` is variable-length: it returns exactly ``event_count``
events. The other eight scenarios are narrative: each has a fixed minimum
size needed to demonstrate its pattern (see ``fixed_scenario_size``), and
``generate_events`` rejects an ``event_count`` below that minimum rather
than silently returning a shorter, unconvincing scenario.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta
from typing import Literal, Protocol

from src.synthetic_realtime.clock import derive_seed, new_rng, require_timezone_aware
from src.synthetic_realtime.contracts import Outcome, SyntheticEvent
from src.synthetic_realtime.features.address import ADDRESS_FAN_OUT_ACCOUNT_THRESHOLD
from src.synthetic_realtime.features.amount import AMOUNT_DEVIATION_THRESHOLD_MULTIPLIER
from src.synthetic_realtime.features.merchant import (
    MERCHANT_FAILURE_RATE_THRESHOLD,
    MERCHANT_MIN_SAMPLE_SIZE,
)
from src.synthetic_realtime.features.retry import (
    ACCOUNT_FAILURE_COUNT_THRESHOLD,
    RETRY_GROUP_SIZE_THRESHOLD,
)

MIN_EVENT_COUNT = 1
MAX_EVENT_COUNT = 500  # generous bound for a synthetic demo/test generator; not a system limit

ScenarioName = Literal[
    "normal_baseline",
    "new_device_burst",
    "address_fan_out",
    "vpn_geography_mismatch",
    "retry_storm",
    "unusual_amount",
    "merchant_deviation",
    "duplicate",
    "out_of_order",
]

_BASELINE_INTERVAL = timedelta(seconds=30)
_BASELINE_COUNTRIES = ("IN", "US", "GB")
_BASELINE_REGIONS = ("APAC", "NA", "EMEA")
_BASELINE_MIN_AMOUNT = 50.0
_BASELINE_MAX_AMOUNT = 5_000.0

_BURST_INTERVAL = timedelta(seconds=10)
_BURST_EVENT_COUNT = 6

_ADDRESS_FAN_OUT_INTERVAL = timedelta(seconds=5)
_ADDRESS_FAN_OUT_EVENT_COUNT = ADDRESS_FAN_OUT_ACCOUNT_THRESHOLD + 2

_VPN_MISMATCH_INTERVAL = timedelta(seconds=30)
_VPN_MISMATCH_EVENT_COUNT = 4

_RETRY_STORM_INTERVAL = timedelta(seconds=5)
_RETRY_STORM_EVENT_COUNT = max(RETRY_GROUP_SIZE_THRESHOLD, ACCOUNT_FAILURE_COUNT_THRESHOLD) + 2

_UNUSUAL_AMOUNT_INTERVAL = timedelta(minutes=10)
_UNUSUAL_AMOUNT_BASELINE_COUNT = 3
_UNUSUAL_AMOUNT_BASELINE_MIN = 50.0
_UNUSUAL_AMOUNT_BASELINE_MAX = 150.0
_UNUSUAL_AMOUNT_SPIKE_MULTIPLIER = AMOUNT_DEVIATION_THRESHOLD_MULTIPLIER + 2.0
_UNUSUAL_AMOUNT_EVENT_COUNT = _UNUSUAL_AMOUNT_BASELINE_COUNT + 1

_MERCHANT_DEVIATION_INTERVAL = timedelta(minutes=1)
_MERCHANT_DEVIATION_EVENT_COUNT = MERCHANT_MIN_SAMPLE_SIZE + 2
_MERCHANT_DEVIATION_FAILING_COUNT = min(
    round(_MERCHANT_DEVIATION_EVENT_COUNT * MERCHANT_FAILURE_RATE_THRESHOLD) + 1,
    _MERCHANT_DEVIATION_EVENT_COUNT,
)

_DUPLICATE_INTERVAL = timedelta(seconds=20)
_DUPLICATE_BASE_COUNT = 3
_DUPLICATE_EVENT_COUNT = _DUPLICATE_BASE_COUNT + 1

# Deliberately non-monotonic arrival order, in seconds from `start`.
_OUT_OF_ORDER_OFFSETS_SECONDS = (0, 120, 30, 150)
_OUT_OF_ORDER_EVENT_COUNT = len(_OUT_OF_ORDER_OFFSETS_SECONDS)


class ScenarioGenerator(Protocol):
    """A named scenario's event-stream generator."""

    def __call__(self, *, seed: int, start: datetime, event_count: int) -> list[SyntheticEvent]: ...


def _token(rng: random.Random, prefix: str) -> str:
    return f"syn_{prefix}_{rng.randint(0, 999):03d}"


def _baseline_amount(rng: random.Random) -> float:
    return round(rng.uniform(_BASELINE_MIN_AMOUNT, _BASELINE_MAX_AMOUNT), 2)


def _generate_normal_baseline(
    *, seed: int, start: datetime, event_count: int
) -> list[SyntheticEvent]:
    """Ordinary traffic: varied merchants/devices/amounts, no anomaly signal."""
    events: list[SyntheticEvent] = []
    for index in range(event_count):
        rng = new_rng(derive_seed(seed, f"normal_baseline:{index}"))
        country = rng.choice(_BASELINE_COUNTRIES)
        region = rng.choice(_BASELINE_REGIONS)
        events.append(
            SyntheticEvent(
                event_id=f"evt_normal_baseline_{index:06d}",
                event_time=start + _BASELINE_INTERVAL * index,
                account_id=_token(rng, "acct"),
                device_id=_token(rng, "dev"),
                payment_method_id=_token(rng, "pm"),
                merchant_id=_token(rng, "mer"),
                address_id=_token(rng, "addr"),
                ip_id=_token(rng, "ip"),
                amount=_baseline_amount(rng),
                currency="INR",
                outcome="success",
                account_country=country,
                event_country=country,
                event_region=region,
                billing_shipping_match=True,
                vpn_or_proxy=False,
                retry_group_id=None,
            )
        )
    return events


def _generate_new_device_burst(
    *, seed: int, start: datetime, event_count: int
) -> list[SyntheticEvent]:
    """One account, a fresh never-before-seen device on every event: repeated
    ``device_new_to_account`` signals."""
    account_rng = new_rng(derive_seed(seed, "new_device_burst:account"))
    account_id = _token(account_rng, "acct")

    events: list[SyntheticEvent] = []
    for index in range(_BURST_EVENT_COUNT):
        rng = new_rng(derive_seed(seed, f"new_device_burst:{index}"))
        events.append(
            SyntheticEvent(
                event_id=f"evt_new_device_burst_{index:06d}",
                event_time=start + _BURST_INTERVAL * index,
                account_id=account_id,
                device_id=_token(rng, "dev"),
                payment_method_id=_token(rng, "pm"),
                merchant_id=_token(rng, "mer"),
                address_id=_token(rng, "addr"),
                ip_id=_token(rng, "ip"),
                amount=_baseline_amount(rng),
                currency="INR",
                outcome="success",
                account_country="IN",
                event_country="IN",
                event_region="APAC",
                billing_shipping_match=True,
                vpn_or_proxy=False,
                retry_group_id=None,
            )
        )
    return events


def _generate_address_fan_out(
    *, seed: int, start: datetime, event_count: int
) -> list[SyntheticEvent]:
    """One address, a fresh distinct account on every event: trips
    ``address_fan_out_high`` once distinct accounts exceed the threshold."""
    address_rng = new_rng(derive_seed(seed, "address_fan_out:address"))
    address_id = _token(address_rng, "addr")

    events: list[SyntheticEvent] = []
    for index in range(_ADDRESS_FAN_OUT_EVENT_COUNT):
        rng = new_rng(derive_seed(seed, f"address_fan_out:{index}"))
        events.append(
            SyntheticEvent(
                event_id=f"evt_address_fan_out_{index:06d}",
                event_time=start + _ADDRESS_FAN_OUT_INTERVAL * index,
                account_id=_token(rng, "acct"),
                device_id=_token(rng, "dev"),
                payment_method_id=_token(rng, "pm"),
                merchant_id=_token(rng, "mer"),
                address_id=address_id,
                ip_id=_token(rng, "ip"),
                amount=_baseline_amount(rng),
                currency="INR",
                outcome="success",
                account_country="IN",
                event_country="IN",
                event_region="APAC",
                billing_shipping_match=True,
                vpn_or_proxy=False,
                retry_group_id=None,
            )
        )
    return events


def _generate_vpn_geography_mismatch(
    *, seed: int, start: datetime, event_count: int
) -> list[SyntheticEvent]:
    """Every event has a mismatched account/event country and vpn_or_proxy=True:
    trips ``geography_country_mismatch`` and ``geography_vpn_or_proxy``."""
    events: list[SyntheticEvent] = []
    for index in range(_VPN_MISMATCH_EVENT_COUNT):
        rng = new_rng(derive_seed(seed, f"vpn_geography_mismatch:{index}"))
        events.append(
            SyntheticEvent(
                event_id=f"evt_vpn_geography_mismatch_{index:06d}",
                event_time=start + _VPN_MISMATCH_INTERVAL * index,
                account_id=_token(rng, "acct"),
                device_id=_token(rng, "dev"),
                payment_method_id=_token(rng, "pm"),
                merchant_id=_token(rng, "mer"),
                address_id=_token(rng, "addr"),
                ip_id=_token(rng, "ip"),
                amount=_baseline_amount(rng),
                currency="INR",
                outcome="success",
                account_country="IN",
                event_country="US",
                event_region="NA",
                billing_shipping_match=True,
                vpn_or_proxy=True,
                retry_group_id=None,
            )
        )
    return events


def _generate_retry_storm(*, seed: int, start: datetime, event_count: int) -> list[SyntheticEvent]:
    """One account/device/payment-method/retry-group, repeated declines then a
    final success: trips ``retry_group_size_high`` and
    ``retry_account_failure_count_high``."""
    account_id = _token(new_rng(derive_seed(seed, "retry_storm:account")), "acct")
    device_id = _token(new_rng(derive_seed(seed, "retry_storm:device")), "dev")
    payment_method_id = _token(new_rng(derive_seed(seed, "retry_storm:pm")), "pm")
    retry_group_id = _token(new_rng(derive_seed(seed, "retry_storm:group")), "retry")

    events: list[SyntheticEvent] = []
    for index in range(_RETRY_STORM_EVENT_COUNT):
        rng = new_rng(derive_seed(seed, f"retry_storm:{index}"))
        outcome: Outcome = "success" if index == _RETRY_STORM_EVENT_COUNT - 1 else "declined"
        events.append(
            SyntheticEvent(
                event_id=f"evt_retry_storm_{index:06d}",
                event_time=start + _RETRY_STORM_INTERVAL * index,
                account_id=account_id,
                device_id=device_id,
                payment_method_id=payment_method_id,
                merchant_id=_token(rng, "mer"),
                address_id=_token(rng, "addr"),
                ip_id=_token(rng, "ip"),
                amount=_baseline_amount(rng),
                currency="INR",
                outcome=outcome,
                account_country="IN",
                event_country="IN",
                event_region="APAC",
                billing_shipping_match=True,
                vpn_or_proxy=False,
                retry_group_id=retry_group_id,
            )
        )
    return events


def _generate_unusual_amount(
    *, seed: int, start: datetime, event_count: int
) -> list[SyntheticEvent]:
    """One account with a modest baseline, then one large spike: trips
    ``amount_unusual_deviation_high``."""
    account_id = _token(new_rng(derive_seed(seed, "unusual_amount:account")), "acct")

    events: list[SyntheticEvent] = []
    baseline_amounts: list[float] = []
    for index in range(_UNUSUAL_AMOUNT_BASELINE_COUNT):
        rng = new_rng(derive_seed(seed, f"unusual_amount:baseline:{index}"))
        amount = round(rng.uniform(_UNUSUAL_AMOUNT_BASELINE_MIN, _UNUSUAL_AMOUNT_BASELINE_MAX), 2)
        baseline_amounts.append(amount)
        events.append(
            SyntheticEvent(
                event_id=f"evt_unusual_amount_{index:06d}",
                event_time=start + _UNUSUAL_AMOUNT_INTERVAL * index,
                account_id=account_id,
                device_id=_token(rng, "dev"),
                payment_method_id=_token(rng, "pm"),
                merchant_id=_token(rng, "mer"),
                address_id=_token(rng, "addr"),
                ip_id=_token(rng, "ip"),
                amount=amount,
                currency="INR",
                outcome="success",
                account_country="IN",
                event_country="IN",
                event_region="APAC",
                billing_shipping_match=True,
                vpn_or_proxy=False,
                retry_group_id=None,
            )
        )

    spike_rng = new_rng(derive_seed(seed, "unusual_amount:spike"))
    baseline_mean = sum(baseline_amounts) / len(baseline_amounts)
    spike_amount = round(baseline_mean * _UNUSUAL_AMOUNT_SPIKE_MULTIPLIER, 2)
    events.append(
        SyntheticEvent(
            event_id=f"evt_unusual_amount_{_UNUSUAL_AMOUNT_BASELINE_COUNT:06d}",
            event_time=start + _UNUSUAL_AMOUNT_INTERVAL * _UNUSUAL_AMOUNT_BASELINE_COUNT,
            account_id=account_id,
            device_id=_token(spike_rng, "dev"),
            payment_method_id=_token(spike_rng, "pm"),
            merchant_id=_token(spike_rng, "mer"),
            address_id=_token(spike_rng, "addr"),
            ip_id=_token(spike_rng, "ip"),
            amount=spike_amount,
            currency="INR",
            outcome="success",
            account_country="IN",
            event_country="IN",
            event_region="APAC",
            billing_shipping_match=True,
            vpn_or_proxy=False,
            retry_group_id=None,
        )
    )
    return events


def _generate_merchant_deviation(
    *, seed: int, start: datetime, event_count: int
) -> list[SyntheticEvent]:
    """One merchant, mostly-declined transactions from varied accounts: trips
    ``merchant_failure_rate_high``."""
    merchant_id = _token(new_rng(derive_seed(seed, "merchant_deviation:merchant")), "mer")

    events: list[SyntheticEvent] = []
    for index in range(_MERCHANT_DEVIATION_EVENT_COUNT):
        rng = new_rng(derive_seed(seed, f"merchant_deviation:{index}"))
        outcome: Outcome = "declined" if index < _MERCHANT_DEVIATION_FAILING_COUNT else "success"
        events.append(
            SyntheticEvent(
                event_id=f"evt_merchant_deviation_{index:06d}",
                event_time=start + _MERCHANT_DEVIATION_INTERVAL * index,
                account_id=_token(rng, "acct"),
                device_id=_token(rng, "dev"),
                payment_method_id=_token(rng, "pm"),
                merchant_id=merchant_id,
                address_id=_token(rng, "addr"),
                ip_id=_token(rng, "ip"),
                amount=_baseline_amount(rng),
                currency="INR",
                outcome=outcome,
                account_country="IN",
                event_country="IN",
                event_region="APAC",
                billing_shipping_match=True,
                vpn_or_proxy=False,
                retry_group_id=None,
            )
        )
    return events


def _generate_duplicate(*, seed: int, start: datetime, event_count: int) -> list[SyntheticEvent]:
    """A short baseline stream, then the first event resubmitted byte-for-byte
    identical later in the stream: an idempotent retry, not a payload
    conflict."""
    events: list[SyntheticEvent] = []
    for index in range(_DUPLICATE_BASE_COUNT):
        rng = new_rng(derive_seed(seed, f"duplicate:{index}"))
        events.append(
            SyntheticEvent(
                event_id=f"evt_duplicate_{index:06d}",
                event_time=start + _DUPLICATE_INTERVAL * index,
                account_id=_token(rng, "acct"),
                device_id=_token(rng, "dev"),
                payment_method_id=_token(rng, "pm"),
                merchant_id=_token(rng, "mer"),
                address_id=_token(rng, "addr"),
                ip_id=_token(rng, "ip"),
                amount=_baseline_amount(rng),
                currency="INR",
                outcome="success",
                account_country="IN",
                event_country="IN",
                event_region="APAC",
                billing_shipping_match=True,
                vpn_or_proxy=False,
                retry_group_id=None,
            )
        )
    events.append(events[0])
    return events


def _generate_out_of_order(*, seed: int, start: datetime, event_count: int) -> list[SyntheticEvent]:
    """Events generated (and thus arriving, in list order) with a deliberately
    non-monotonic ``event_time`` sequence, to demonstrate late/out-of-order
    detection when replayed through a store in this exact order."""
    events: list[SyntheticEvent] = []
    for index, offset_seconds in enumerate(_OUT_OF_ORDER_OFFSETS_SECONDS):
        rng = new_rng(derive_seed(seed, f"out_of_order:{index}"))
        events.append(
            SyntheticEvent(
                event_id=f"evt_out_of_order_{index:06d}",
                event_time=start + timedelta(seconds=offset_seconds),
                account_id=_token(rng, "acct"),
                device_id=_token(rng, "dev"),
                payment_method_id=_token(rng, "pm"),
                merchant_id=_token(rng, "mer"),
                address_id=_token(rng, "addr"),
                ip_id=_token(rng, "ip"),
                amount=_baseline_amount(rng),
                currency="INR",
                outcome="success",
                account_country="IN",
                event_country="IN",
                event_region="APAC",
                billing_shipping_match=True,
                vpn_or_proxy=False,
                retry_group_id=None,
            )
        )
    return events


_SCENARIO_GENERATORS: dict[ScenarioName, ScenarioGenerator] = {
    "normal_baseline": _generate_normal_baseline,
    "new_device_burst": _generate_new_device_burst,
    "address_fan_out": _generate_address_fan_out,
    "vpn_geography_mismatch": _generate_vpn_geography_mismatch,
    "retry_storm": _generate_retry_storm,
    "unusual_amount": _generate_unusual_amount,
    "merchant_deviation": _generate_merchant_deviation,
    "duplicate": _generate_duplicate,
    "out_of_order": _generate_out_of_order,
}

# The exact event count each narrative scenario always returns. Absent here
# (normal_baseline) means variable-length: it returns exactly `event_count`.
_FIXED_NARRATIVE_SIZES: dict[ScenarioName, int] = {
    "new_device_burst": _BURST_EVENT_COUNT,
    "address_fan_out": _ADDRESS_FAN_OUT_EVENT_COUNT,
    "vpn_geography_mismatch": _VPN_MISMATCH_EVENT_COUNT,
    "retry_storm": _RETRY_STORM_EVENT_COUNT,
    "unusual_amount": _UNUSUAL_AMOUNT_EVENT_COUNT,
    "merchant_deviation": _MERCHANT_DEVIATION_EVENT_COUNT,
    "duplicate": _DUPLICATE_EVENT_COUNT,
    "out_of_order": _OUT_OF_ORDER_EVENT_COUNT,
}


def available_scenarios() -> tuple[ScenarioName, ...]:
    """Return the currently implemented scenario names, in registry order."""
    return tuple(_SCENARIO_GENERATORS.keys())


def fixed_scenario_size(scenario: ScenarioName) -> int | None:
    """The exact event count a narrative scenario always returns.

    Returns None for a variable-length scenario (``normal_baseline``), which
    instead always returns exactly the requested ``event_count``.
    """
    if scenario not in _SCENARIO_GENERATORS:
        raise ValueError(f"Unknown scenario {scenario!r}. Known scenarios: {available_scenarios()}")
    return _FIXED_NARRATIVE_SIZES.get(scenario)


def generate_events(
    scenario: ScenarioName, *, seed: int, start: datetime, event_count: int
) -> list[SyntheticEvent]:
    """Deterministically generate a named scenario's event stream.

    Calling this twice with identical arguments always returns events that
    compare equal. The returned ``SyntheticEvent`` objects are immutable, so
    the list can be safely reused across callers.

    For a narrative scenario, ``event_count`` is a floor: it must be at
    least ``fixed_scenario_size(scenario)`` or this raises, since a shorter
    stream wouldn't actually demonstrate the scenario's pattern. The
    returned list is always exactly ``fixed_scenario_size(scenario)`` long
    regardless of how much higher ``event_count`` was set.
    """
    if scenario not in _SCENARIO_GENERATORS:
        raise ValueError(f"Unknown scenario {scenario!r}. Known scenarios: {available_scenarios()}")
    if not MIN_EVENT_COUNT <= event_count <= MAX_EVENT_COUNT:
        raise ValueError(f"event_count must be between {MIN_EVENT_COUNT} and {MAX_EVENT_COUNT}.")
    require_timezone_aware(start, field_name="start")

    minimum_required = _FIXED_NARRATIVE_SIZES.get(scenario)
    if minimum_required is not None and event_count < minimum_required:
        raise ValueError(
            f"Scenario {scenario!r} needs at least {minimum_required} events to "
            f"demonstrate its pattern; got event_count={event_count}."
        )

    generator = _SCENARIO_GENERATORS[scenario]
    return generator(seed=seed, start=start, event_count=event_count)
