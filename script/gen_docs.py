"""Generate the documentation blocks that must match the code.

    python script/gen_docs.py          # rewrite the generated blocks
    python script/gen_docs.py --check  # exit 1 when a block differs from the code

Only the text between `<!-- BEGIN GENERATED: <name> (script/gen_docs.py) -->` and
`<!-- END GENERATED: <name> -->` is written; everything around it stays hand-written.
Run it with the test environment (`requirements_test.txt`): it imports the integration.
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from string import Template
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from script.docs_attributes import (  # noqa: E402
    ALL_CLEAR_TEXT,
    ATTRIBUTES,
    RECOMMENDATION_TEXTS,
)

PACKAGE = ROOT / "custom_components" / "haghs"
UNRECORDED_NOTE = "current only, excluded from recorder history"
REGENERATE = "python script/gen_docs.py"


class GenDocsError(Exception):
    """The code and the documentation sources do not fit together."""


@dataclass(frozen=True)
class OptionField:
    """One field of the options form."""

    key: str
    default: Any  # None when the field has no default
    minimum: float | None = None
    maximum: float | None = None
    unit: str | None = None
    choices: tuple[str, ...] = ()


@dataclass(frozen=True)
class Sources:
    """Everything the generated blocks are made from, read from the code."""

    attribute_keys: tuple[str, ...]
    unrecorded: frozenset[str]
    constants: Mapping[str, Any]
    strings: Mapping[str, Any]
    options: tuple[OptionField, ...]
    attributes: Mapping[str, tuple[str, str]] = field(default_factory=lambda: ATTRIBUTES)
    recommendation_texts: Mapping[str, tuple[str, ...]] = field(
        default_factory=lambda: RECOMMENDATION_TEXTS
    )


def published_attribute_keys(sensor_source: str, rec_flag_keys: tuple[str, ...]) -> tuple[str, ...]:
    """Keys of `HaghsSensor.extra_state_attributes`, in order, with `**REC_FLAG_KEYS` expanded."""
    for node in ast.walk(ast.parse(sensor_source)):
        if isinstance(node, ast.FunctionDef) and node.name == "extra_state_attributes":
            returned = [n.value for n in ast.walk(node) if isinstance(n, ast.Return)]
            mapping = next(v for v in returned if isinstance(v, ast.Dict))
            keys: list[str] = []
            for key in mapping.keys:
                if key is None:  # **{k: data[k] for k in REC_FLAG_KEYS}
                    keys.extend(rec_flag_keys)
                elif isinstance(key, ast.Constant) and isinstance(key.value, str):
                    keys.append(key.value)
                else:
                    raise GenDocsError(f"unsupported attribute key in sensor.py: {ast.dump(key)}")
            return tuple(keys)
    raise GenDocsError("sensor.py has no extra_state_attributes")


def _option_field(marker: Any, field_selector: Any) -> OptionField:
    from homeassistant.helpers import selector

    default = marker.default() if callable(marker.default) else None
    config = getattr(field_selector, "config", {})
    if isinstance(field_selector, selector.NumberSelector):
        return OptionField(
            str(marker),
            default,
            config.get("min"),
            config.get("max"),
            config.get("unit_of_measurement"),
        )
    if isinstance(field_selector, selector.SelectSelector):
        choices = tuple(
            option if isinstance(option, str) else option["value"]
            for option in config.get("options", [])
        )
        return OptionField(str(marker), default, choices=choices)
    return OptionField(str(marker), default)


def option_fields() -> tuple[OptionField, ...]:
    """Fields of the options form in form order (the form's own schema parts)."""
    import voluptuous as vol

    from custom_components.haghs import config_flow
    from custom_components.haghs.const import CONF_IGNORED_INTEGRATION_ENTRIES

    fields = [
        _option_field(vol.Optional(key), field_selector)
        for key, field_selector in config_flow.FALLBACK_SENSORS_SCHEMA.items()
    ]
    for part in (config_flow._BASE_SCHEMA, config_flow._EXTRA_OPTIONS_SCHEMA):
        fields.extend(_option_field(marker, value) for marker, value in part.items())
    # Built inside async_step_init from the live config entries: a multi-select without default.
    fields.append(OptionField(CONF_IGNORED_INTEGRATION_ENTRIES, None))
    return tuple(fields)


def load_sources(root: Path = ROOT) -> Sources:
    """Read every source of the generated blocks from the integration."""
    from custom_components.haghs import const
    from custom_components.haghs.sensor import HaghsSensor

    package = root / "custom_components" / "haghs"
    return Sources(
        attribute_keys=published_attribute_keys(
            (package / "sensor.py").read_text(encoding="utf-8"), const.REC_FLAG_KEYS
        ),
        unrecorded=frozenset(HaghsSensor._unrecorded_attributes),
        constants={name: getattr(const, name) for name in dir(const) if name.isupper()},
        strings=json.loads((package / "strings.json").read_text(encoding="utf-8")),
        options=option_fields(),
    )


def _cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def _number(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else str(value)


def render_attributes(src: Sources) -> str:
    """The full attribute table of docs/attributes.md."""
    published, documented = set(src.attribute_keys), set(src.attributes)
    if missing := sorted(published - documented):
        raise GenDocsError(f"attributes without a row in script/docs_attributes.py: {missing}")
    if extra := sorted(documented - published):
        raise GenDocsError(f"rows for attributes the sensor does not publish: {extra}")
    rows = ["| Attribute | Type | Description |", "|---|---|---|"]
    for key in src.attribute_keys:
        kind, template = src.attributes[key]
        has_note = "$unrecorded" in template
        if has_note != (key in src.unrecorded):
            raise GenDocsError(
                f"{key}: the recorder note ($unrecorded) must be present exactly when the attribute "
                "is in HaghsSensor._unrecorded_attributes"
            )
        try:
            text = Template(template).substitute(src.constants, unrecorded=UNRECORDED_NOTE)
        except (KeyError, ValueError) as err:
            raise GenDocsError(f"{key}: unknown placeholder {err}") from err
        rows.append(f"| `{key}` | {kind} | {_cell(text)} |")
    return "\n".join(rows)


def render_recommendations(src: Sources) -> str:
    """Every recommendation flag with the English text it adds to `recommendations`."""
    common = src.strings["common"]
    texts = {key for key in common if key.startswith("rec_")} - {ALL_CLEAR_TEXT}
    mapped = [key for keys in src.recommendation_texts.values() for key in keys]
    if sorted(mapped) != sorted(texts):
        raise GenDocsError(
            "recommendation texts in strings.json common and RECOMMENDATION_TEXTS differ: "
            f"unmapped {sorted(texts - set(mapped))}, unknown {sorted(set(mapped) - texts)}"
        )
    flags = [key for key in src.attribute_keys if key.startswith("rec_")]
    if sorted(flags) != sorted(src.recommendation_texts):
        raise GenDocsError(
            f"recommendation flags and RECOMMENDATION_TEXTS differ: {sorted(flags)} "
            f"vs {sorted(src.recommendation_texts)}"
        )
    rows = ["| Flag | Recommendation text (English template) |", "|---|---|"]
    for flag in flags:
        lines = "<br>".join(f"`{_cell(common[key])}`" for key in src.recommendation_texts[flag])
        rows.append(f"| `{flag}` | {lines} |")
    rows.append(f"| (none set) | `{_cell(common[ALL_CLEAR_TEXT])}` |")
    return "\n".join(rows)


def render_options(src: Sources) -> str:
    """Every field of the options form with label, description, default and range."""
    step = src.strings["options"]["step"]["init"]
    labels, descriptions = step["data"], step["data_description"]
    keys = [option.key for option in src.options]
    if sorted(keys) != sorted(labels):
        raise GenDocsError(
            f"options form fields and strings.json labels differ: {sorted(keys)} vs {sorted(labels)}"
        )
    rows = ["| Option | Default | Range | Description |", "|---|---|---|---|"]
    for option in src.options:
        default = "none" if option.default is None else f"`{option.default}`"
        if option.minimum is not None and option.maximum is not None:
            span = f"{_number(option.minimum)}\u2013{_number(option.maximum)}"
            span += f" {option.unit}" if option.unit else ""
        elif option.choices:
            span = ", ".join(f"`{choice}`" for choice in option.choices)
        else:
            span = "\u2013"
        rows.append(
            f"| **{_cell(labels[option.key])}** | {default} | {span} | "
            f"{_cell(descriptions.get(option.key, ''))} |"
        )
    return "\n".join(rows)


# (file relative to the repository root, block name) -> renderer
BLOCKS: dict[tuple[str, str], Callable[[Sources], str]] = {
    ("docs/attributes.md", "attributes"): render_attributes,
    ("docs/attributes.md", "recommendations"): render_recommendations,
    ("docs/configuration.md", "options"): render_options,
}


def replace_block(text: str, name: str, content: str) -> str:
    """Put `content` between the markers of block `name`; the markers must exist exactly once."""
    begin = f"<!-- BEGIN GENERATED: {name} (script/gen_docs.py) -->"
    end = f"<!-- END GENERATED: {name} -->"
    if text.count(begin) != 1 or text.count(end) != 1 or text.index(begin) > text.index(end):
        raise GenDocsError(f"block {name}: markers missing or not exactly once")
    head, rest = text.split(begin)
    _, tail = rest.split(end)
    return f"{head}{begin}\n{content}\n{end}{tail}"


def generate(root: Path = ROOT, src: Sources | None = None) -> dict[Path, str]:
    """The expected content of every file with generated blocks."""
    src = src or load_sources(root)
    result: dict[Path, str] = {}
    for (name, block), render in BLOCKS.items():
        path = root / name
        text = result.get(path, path.read_text(encoding="utf-8"))
        result[path] = replace_block(text, block, render(src))
    return result


def main(argv: list[str] | None = None) -> int:
    """Write the generated blocks, or with --check report files that differ."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="only compare, write nothing")
    args = parser.parse_args(argv)
    try:
        expected = generate()
    except GenDocsError as err:
        print(f"gen_docs: {err}", file=sys.stderr)
        return 1
    stale = [path for path, text in expected.items() if path.read_text(encoding="utf-8") != text]
    if args.check:
        for path in stale:
            print(f"{path.relative_to(ROOT)} is out of date; run: {REGENERATE}", file=sys.stderr)
        return 1 if stale else 0
    for path in stale:
        path.write_text(expected[path], encoding="utf-8")
        print(f"updated {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
