from __future__ import annotations

from limiter.rules import RULES


def test_every_rule_has_positive_bounds() -> None:
    for key, rule in RULES.items():
        assert rule.capacity > 0, key
        assert rule.refill_rate > 0, key
        assert rule.ttl_seconds > 0, key
