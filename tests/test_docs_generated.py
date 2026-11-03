"""Generated documentation blocks match the code (script/gen_docs.py)."""

from __future__ import annotations

import dataclasses
import re
from pathlib import Path

import pytest
from homeassistant.core import HomeAssistant

from custom_components.haghs.const import DOMAIN
from custom_components.haghs.sensor import HaghsSensor
from script import gen_docs
from script.docs_attributes import ATTRIBUTES
from tests.factories import make_coordinator, patch_disk, patch_psi

ROOT = Path(__file__).resolve().parent.parent
# Python types a documented attribute type allows; bool is not an int here.
TYPES = {
    "int": (int,),
    "float": (float,),
    "bool": (bool,),
    "list": (list,),
    "dict": (dict,),
    "string": (str,),
    "str/null": (str, type(None)),
    "int/null": (int, type(None)),
}
TEST_COUNT = re.compile(r"\b\d[\d,.]*\s+tests?\b", re.IGNORECASE)


@pytest.fixture(scope="module")
def sources() -> gen_docs.Sources:
    return gen_docs.load_sources()


def test_generated_blocks_match_the_files(sources: gen_docs.Sources) -> None:
    stale = [
        str(path.relative_to(ROOT))
        for path, text in gen_docs.generate(ROOT, sources).items()
        if path.read_text(encoding="utf-8") != text
    ]
    assert stale == [], f"out of date: {stale}; run: python script/gen_docs.py"


def test_check_mode_exits_zero_on_the_repository() -> None:
    assert gen_docs.main(["--check"]) == 0


def test_check_mode_reports_a_stale_file(tmp_path, monkeypatch, capsys) -> None:
    for name in {name for name, _ in gen_docs.BLOCKS}:
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text((ROOT / name).read_text(encoding="utf-8"), encoding="utf-8")
    stale = tmp_path / "docs/attributes.md"
    stale.write_text(stale.read_text(encoding="utf-8").replace("capped at 100", "capped at 99", 1))
    real_generate = gen_docs.generate
    monkeypatch.setattr(gen_docs, "ROOT", tmp_path)
    sources = gen_docs.load_sources()
    monkeypatch.setattr(gen_docs, "generate", lambda: real_generate(tmp_path, sources))
    assert gen_docs.main(["--check"]) == 1
    assert (
        "docs/attributes.md is out of date; run: python script/gen_docs.py"
        in capsys.readouterr().err
    )
    assert gen_docs.main([]) == 0
    assert gen_docs.main(["--check"]) == 0
    assert stale.read_text(encoding="utf-8") == (ROOT / "docs/attributes.md").read_text(
        encoding="utf-8"
    )


def test_every_published_attribute_has_a_row(sources: gen_docs.Sources) -> None:
    assert list(sources.attribute_keys) == list(dict.fromkeys(sources.attribute_keys))
    assert set(sources.attribute_keys) == set(ATTRIBUTES)


def test_new_attribute_without_a_row_fails(sources: gen_docs.Sources) -> None:
    src = dataclasses.replace(sources, attribute_keys=(*sources.attribute_keys, "new_attribute"))
    with pytest.raises(gen_docs.GenDocsError, match=r"without a row.*new_attribute"):
        gen_docs.render_attributes(src)


def test_removed_attribute_fails(sources: gen_docs.Sources) -> None:
    keys = tuple(key for key in sources.attribute_keys if key != "zombie_since")
    src = dataclasses.replace(sources, attribute_keys=keys)
    with pytest.raises(gen_docs.GenDocsError, match=r"does not publish.*zombie_since"):
        gen_docs.render_attributes(src)


def test_recorder_note_follows_the_unrecorded_set(sources: gen_docs.Sources) -> None:
    assert "current only, excluded from recorder history" in gen_docs.render_attributes(sources)
    for unrecorded in (
        sources.unrecorded - {"zombie_since"},
        sources.unrecorded | {"zombie_count"},
    ):
        src = dataclasses.replace(sources, unrecorded=frozenset(unrecorded))
        with pytest.raises(gen_docs.GenDocsError, match="recorder note"):
            gen_docs.render_attributes(src)


def test_changed_cap_changes_the_table(sources: gen_docs.Sources) -> None:
    before = gen_docs.render_attributes(sources)
    src = dataclasses.replace(sources, constants={**sources.constants, "ZOMBIE_LIST_CAP": 250})
    after = gen_docs.render_attributes(src)
    assert after != before
    assert "Entity IDs of zombies (capped at 250;" in after
    assert "same 250 entries and order as `zombie_entities`" in after


def test_unknown_placeholder_fails(sources: gen_docs.Sources) -> None:
    attributes = {**ATTRIBUTES, "zombie_count": ("int", "capped at ${NO_SUCH_CAP}")}
    src = dataclasses.replace(sources, attributes=attributes)
    with pytest.raises(gen_docs.GenDocsError, match="unknown placeholder"):
        gen_docs.render_attributes(src)


def test_changed_default_changes_the_options_table(sources: gen_docs.Sources) -> None:
    before = gen_docs.render_options(sources)
    options = tuple(
        dataclasses.replace(field, default=120) if field.key == "update_interval" else field
        for field in sources.options
    )
    after = gen_docs.render_options(dataclasses.replace(sources, options=options))
    assert after != before
    assert "| **Update interval** | `120` | 10\u20133600 s |" in after


def test_options_table_reads_defaults_and_ranges_from_the_form(sources: gen_docs.Sources) -> None:
    table = gen_docs.render_options(sources)
    assert "| **Update interval** | `60` | 10\u20133600 s |" in table
    assert "| **Zombie grace period (minutes)** | `5` | 1\u2013240 min |" in table
    assert "| **Battery-class grace period (minutes)** | `60` | 1\u2013240 min |" in table
    assert "| **Stale threshold (hours)** | `24` | 1\u20138760 h |" in table
    assert "| **Storage type** | `sd-card` | `sd-card`, `ssd`, `emmc` |" in table
    assert "| **CPU usage sensor** | none | \u2013 |" in table


def test_option_field_without_label_fails(sources: gen_docs.Sources) -> None:
    options = (*sources.options, gen_docs.OptionField("new_option", None))
    with pytest.raises(gen_docs.GenDocsError, match="options form fields"):
        gen_docs.render_options(dataclasses.replace(sources, options=options))


def test_option_field_without_description_fails(sources: gen_docs.Sources) -> None:
    init = sources.strings["options"]["step"]["init"]
    descriptions = {k: v for k, v in init["data_description"].items() if k != "update_interval"}
    strings = {
        **sources.strings,
        "options": {"step": {"init": {**init, "data_description": descriptions}}},
    }
    with pytest.raises(gen_docs.GenDocsError, match=r"data_description.*update_interval"):
        gen_docs.render_options(dataclasses.replace(sources, strings=strings))


@pytest.mark.parametrize(
    "source",
    [
        "class S:\n    def other(self):\n        return {}\n",
        "class S:\n    def extra_state_attributes(self):\n        return None\n",
    ],
)
def test_sensor_without_attribute_dict_fails(source: str) -> None:
    with pytest.raises(gen_docs.GenDocsError, match="extra_state_attributes"):
        gen_docs.published_attribute_keys(source, ())


def test_changed_recommendation_text_changes_the_table(sources: gen_docs.Sources) -> None:
    before = gen_docs.render_recommendations(sources)
    common = {**sources.strings["common"], "rec_core_lag": "Core is old."}
    src = dataclasses.replace(sources, strings={**sources.strings, "common": common})
    after = gen_docs.render_recommendations(src)
    assert after != before
    assert "| `rec_core_lag` | `Core is old.` |" in after


def test_unmapped_recommendation_text_fails(sources: gen_docs.Sources) -> None:
    common = {**sources.strings["common"], "rec_new_text": "New."}
    src = dataclasses.replace(sources, strings={**sources.strings, "common": common})
    with pytest.raises(gen_docs.GenDocsError, match=r"unmapped \['rec_new_text'\]"):
        gen_docs.render_recommendations(src)


def test_recommendation_flag_without_text_fails(sources: gen_docs.Sources) -> None:
    src = dataclasses.replace(sources, attribute_keys=(*sources.attribute_keys, "rec_new_flag"))
    with pytest.raises(gen_docs.GenDocsError, match="recommendation flags"):
        gen_docs.render_recommendations(src)


def test_missing_markers_fail() -> None:
    with pytest.raises(gen_docs.GenDocsError, match="markers"):
        gen_docs.replace_block("no markers here", "attributes", "x")


async def test_documented_types_match_a_real_update(hass: HomeAssistant) -> None:
    """Every published value of a healthy update has the documented type."""
    coord = make_coordinator(hass)
    with patch_psi(cpu=1.0, memory=1.0, io=1.0), patch_disk():
        hw = await coord._async_calc_hardware()
        app = await coord._async_calc_application()
    coord.data = coord._build_result(hw, app)
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    attributes = HaghsSensor(coord, entry).extra_state_attributes
    assert set(attributes) == set(ATTRIBUTES)
    wrong = {
        key: type(value).__name__
        for key, value in attributes.items()
        if not isinstance(value, TYPES[ATTRIBUTES[key][0]])
        or (isinstance(value, bool) and ATTRIBUTES[key][0] != "bool")
    }
    assert wrong == {}


def test_no_hand_written_test_count_in_user_docs() -> None:
    files = [ROOT / "README.md", ROOT / "ROADMAP.md", *sorted((ROOT / "docs").rglob("*.md"))]
    found = [
        f"{path.relative_to(ROOT)}:{number}: {match.group(0)}"
        for path in files
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if (match := TEST_COUNT.search(line))
    ]
    assert found == []


def test_test_count_pattern_matches_counts_only() -> None:
    assert TEST_COUNT.search("The suite holds 663 tests.")
    assert TEST_COUNT.search("1,024 Tests pass")
    assert not TEST_COUNT.search("unit tests run in CI")
