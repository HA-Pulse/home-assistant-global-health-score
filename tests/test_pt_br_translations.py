"""Keep Brazilian Portuguese aligned with the existing English translation schema."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from string import Formatter

import pytest

TRANSLATIONS = Path(__file__).resolve().parents[1] / "custom_components/haghs/translations"


def _assert_translation_matches(reference: object, translated: object, path: str = "") -> None:
    """Check the complete schema and format fields without interpreting translations."""
    assert type(translated) is type(reference), f"{path}: translation type differs"
    if isinstance(reference, dict):
        assert isinstance(translated, dict)
        assert reference.keys() == translated.keys(), f"{path}: translation keys differ"
        for key, value in reference.items():
            _assert_translation_matches(value, translated[key], f"{path}.{key}")
    elif isinstance(reference, str):
        assert isinstance(translated, str)
        assert translated.strip(), f"{path}: empty translation"
        formatter = Formatter()
        expected = Counter(
            (field, spec, conversion)
            for _, field, spec, conversion in formatter.parse(reference)
            if field is not None
        )
        actual = Counter(
            (field, spec, conversion)
            for _, field, spec, conversion in formatter.parse(translated)
            if field is not None
        )
        assert actual == expected, f"{path}: translation placeholders differ"
    else:
        assert translated == reference, f"{path}: non-text value differs"


def test_pt_br_matches_complete_english_schema() -> None:
    """Every English key, leaf type and format field must also exist in pt-BR."""
    english = json.loads((TRANSLATIONS / "en.json").read_text(encoding="utf-8"))
    portuguese = json.loads((TRANSLATIONS / "pt-BR.json").read_text(encoding="utf-8"))
    _assert_translation_matches(english, portuguese)


@pytest.mark.parametrize(
    ("translated", "message"),
    [
        ({}, "translation keys differ"),
        ({"message": "Texto", "extra": "Texto"}, "translation keys differ"),
        ({"message": 5}, "translation type differs"),
        ({"message": "  "}, "empty translation"),
        ({"message": "Valor {other:.1f}"}, "translation placeholders differ"),
        ({"message": "Valor {value}"}, "translation placeholders differ"),
        ({"message": "Valor {value!r:.1f}"}, "translation placeholders differ"),
        ({"message": "Valor {value:.1f} {value:.1f}"}, "translation placeholders differ"),
    ],
    ids=[
        "missing-key",
        "extra-key",
        "wrong-type",
        "blank",
        "wrong-field",
        "wrong-spec",
        "wrong-conversion",
        "duplicate-field",
    ],
)
def test_schema_check_rejects_broken_translations(translated: dict, message: str) -> None:
    """Synthetic defects must be rejected by the same assertion as the real file."""
    with pytest.raises(AssertionError, match=message):
        _assert_translation_matches({"message": "Value {value:.1f}"}, translated)


def test_schema_check_accepts_reordered_fields_and_escaped_braces() -> None:
    """Word order may differ while escaped braces remain literal text."""
    _assert_translation_matches(
        {"message": "{{Value}} {value:.1f} {count}"},
        {"message": "{count}: {{Valor}} {value:.1f}"},
    )


def test_schema_check_rejects_malformed_format_string() -> None:
    """An unmatched brace must never silently pass placeholder validation."""
    with pytest.raises(ValueError, match="Single"):
        _assert_translation_matches({"message": "Value"}, {"message": "Valor }"})
