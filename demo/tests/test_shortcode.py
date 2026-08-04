from __future__ import annotations

from demo.shortcode import ALPHABET, CODE_LENGTH, generate_code


def test_code_length_and_charset() -> None:
    code = generate_code()
    assert len(code) == CODE_LENGTH
    assert all(c in ALPHABET for c in code)


def test_codes_are_unique_in_batch() -> None:
    codes = {generate_code() for _ in range(100)}
    assert len(codes) == 100
