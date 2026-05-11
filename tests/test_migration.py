"""Migration tests for HAGHS config entries (issue #54, phase 2)."""

from __future__ import annotations

from unittest.mock import MagicMock

from homeassistant.core import HomeAssistant
from homeassistant.helpers import label_registry as lr
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.haghs import (
    _migrate_ignore_label_value,
    async_migrate_entry,
)
from custom_components.haghs.const import _CONFIG_VERSION, CONF_IGNORE_LABEL, DOMAIN


def _mock_registry(
    *,
    label_by_id: object = None,
    label_by_name_responses: list[object] | None = None,
    create_side_effect: object = None,
    create_return: object = None,
) -> MagicMock:
    """Build a MagicMock LabelRegistry with controlled responses."""
    registry = MagicMock(spec=lr.LabelRegistry)
    registry.async_get_label.return_value = label_by_id
    if label_by_name_responses is not None:
        registry.async_get_label_by_name.side_effect = label_by_name_responses
    else:
        registry.async_get_label_by_name.return_value = None
    if create_side_effect is not None:
        registry.async_create.side_effect = create_side_effect
    else:
        registry.async_create.return_value = create_return
    return registry


# ============================================================================
# _migrate_ignore_label_value — branch coverage with mocked LabelRegistry
# ============================================================================


def test_no_ignore_label_key() -> None:
    """CONF_IGNORE_LABEL key absent in config dict gives a clean no-op."""
    registry = _mock_registry()
    config: dict = {}

    assert _migrate_ignore_label_value(registry, config) is True
    assert config == {}
    registry.async_get_label.assert_not_called()
    registry.async_create.assert_not_called()


def test_empty_string_value() -> None:
    """Empty string is treated as no value."""
    registry = _mock_registry()
    config = {CONF_IGNORE_LABEL: ""}

    assert _migrate_ignore_label_value(registry, config) is True
    assert config == {CONF_IGNORE_LABEL: ""}
    registry.async_get_label.assert_not_called()


def test_none_value() -> None:
    """None is treated as no value."""
    registry = _mock_registry()
    config = {CONF_IGNORE_LABEL: None}

    assert _migrate_ignore_label_value(registry, config) is True
    assert config == {CONF_IGNORE_LABEL: None}
    registry.async_get_label.assert_not_called()


def test_already_label_id_is_idempotent() -> None:
    """B2 guard: a value that is already a known label ID skips conversion."""
    existing = MagicMock(label_id="haghs_ignore")
    registry = _mock_registry(label_by_id=existing)
    config = {CONF_IGNORE_LABEL: "haghs_ignore"}

    assert _migrate_ignore_label_value(registry, config) is True
    assert config == {CONF_IGNORE_LABEL: "haghs_ignore"}
    registry.async_get_label_by_name.assert_not_called()
    registry.async_create.assert_not_called()


def test_label_name_existing_resolved_to_id() -> None:
    """A known label name is rewritten to its label_id."""
    found = MagicMock(label_id="my_ignore_label")
    registry = _mock_registry(label_by_name_responses=[found])
    config = {CONF_IGNORE_LABEL: "My Ignore Label"}

    assert _migrate_ignore_label_value(registry, config) is True
    assert config[CONF_IGNORE_LABEL] == "my_ignore_label"
    registry.async_create.assert_not_called()


def test_label_name_unknown_creates_label() -> None:
    """Unknown label name leads to async_create being called once."""
    created = MagicMock(label_id="new_label")
    registry = _mock_registry(create_return=created)
    config = {CONF_IGNORE_LABEL: "New Label"}

    assert _migrate_ignore_label_value(registry, config) is True
    assert config[CONF_IGNORE_LABEL] == "new_label"
    registry.async_create.assert_called_once_with("New Label")


def test_create_raises_second_lookup_finds_label() -> None:
    """ValueError on async_create + second name lookup finds the racing label."""
    found_after_race = MagicMock(label_id="race_label")
    registry = _mock_registry(
        label_by_name_responses=[None, found_after_race],
        create_side_effect=ValueError("already exists"),
    )
    config = {CONF_IGNORE_LABEL: "Race Label"}

    assert _migrate_ignore_label_value(registry, config) is True
    assert config[CONF_IGNORE_LABEL] == "race_label"
    assert registry.async_get_label_by_name.call_count == 2


def test_create_raises_second_lookup_misses_pops_value(caplog) -> None:
    """ValueError + second lookup also missing pops the key and warns."""
    registry = _mock_registry(
        label_by_name_responses=[None, None],
        create_side_effect=ValueError("collision"),
    )
    config = {CONF_IGNORE_LABEL: "Lost Label"}

    with caplog.at_level("WARNING"):
        assert _migrate_ignore_label_value(registry, config) is True

    assert CONF_IGNORE_LABEL not in config
    assert "Could not migrate ignore label" in caplog.text


# ============================================================================
# async_migrate_entry — integration with real hass + MockConfigEntry
# ============================================================================


async def test_migrate_from_v2_0_bumps_version_and_rewrites_label(
    hass: HomeAssistant,
) -> None:
    """v2.0 entry is migrated to the current version and label is converted."""
    label_registry = lr.async_get(hass)
    label = label_registry.async_create("Legacy Label")

    entry = MockConfigEntry(
        domain=DOMAIN,
        version=2,
        minor_version=0,
        data={CONF_IGNORE_LABEL: "Legacy Label"},
        options={},
    )
    entry.add_to_hass(hass)

    assert await async_migrate_entry(hass, entry) is True
    assert entry.version == _CONFIG_VERSION.major
    assert entry.minor_version == _CONFIG_VERSION.minor
    assert entry.data[CONF_IGNORE_LABEL] == label.label_id


async def test_migrate_from_v3_1_only_touches_label_field(
    hass: HomeAssistant,
) -> None:
    """v3.1 entry is bumped to the current version; other fields are preserved."""
    label_registry = lr.async_get(hass)
    label = label_registry.async_create("Older Label")

    entry = MockConfigEntry(
        domain=DOMAIN,
        version=3,
        minor_version=1,
        data={
            CONF_IGNORE_LABEL: "Older Label",
            "cpu_sensor": "sensor.cpu_use",
            "storage_type": "ssd",
        },
        options={},
    )
    entry.add_to_hass(hass)

    assert await async_migrate_entry(hass, entry) is True
    assert entry.version == _CONFIG_VERSION.major
    assert entry.minor_version == _CONFIG_VERSION.minor
    assert entry.data[CONF_IGNORE_LABEL] == label.label_id
    assert entry.data["cpu_sensor"] == "sensor.cpu_use"
    assert entry.data["storage_type"] == "ssd"


async def test_migrate_from_v3_2_bumps_to_current_without_label_work(
    hass: HomeAssistant,
) -> None:
    """v3.2 entry already holds a label_id and only needs the version bump."""
    label_registry = lr.async_get(hass)
    label = label_registry.async_create("Ignore Me")

    entry = MockConfigEntry(
        domain=DOMAIN,
        version=3,
        minor_version=2,
        data={CONF_IGNORE_LABEL: label.label_id},
        options={},
    )
    entry.add_to_hass(hass)

    assert await async_migrate_entry(hass, entry) is True
    assert entry.version == _CONFIG_VERSION.major
    assert entry.minor_version == _CONFIG_VERSION.minor
    assert entry.data[CONF_IGNORE_LABEL] == label.label_id

    # B2 regression: no second label was created whose name equals the ID.
    assert label_registry.async_get_label_by_name(label.label_id) is None


async def test_migrate_at_current_version_is_noop(hass: HomeAssistant) -> None:
    """An entry already at _CONFIG_VERSION returns early without touching data."""
    label_registry = lr.async_get(hass)
    label = label_registry.async_create("Already Done")

    entry = MockConfigEntry(
        domain=DOMAIN,
        version=_CONFIG_VERSION.major,
        minor_version=_CONFIG_VERSION.minor,
        data={CONF_IGNORE_LABEL: label.label_id},
        options={},
    )
    entry.add_to_hass(hass)

    assert await async_migrate_entry(hass, entry) is True
    assert entry.version == _CONFIG_VERSION.major
    assert entry.minor_version == _CONFIG_VERSION.minor
    assert entry.data[CONF_IGNORE_LABEL] == label.label_id


async def test_migrate_handles_data_and_options_independently(
    hass: HomeAssistant,
) -> None:
    """Both entry.data and entry.options are migrated in a single run."""
    label_registry = lr.async_get(hass)
    data_label = label_registry.async_create("Data Label")
    options_label = label_registry.async_create("Options Label")

    entry = MockConfigEntry(
        domain=DOMAIN,
        version=3,
        minor_version=0,
        data={CONF_IGNORE_LABEL: "Data Label"},
        options={CONF_IGNORE_LABEL: "Options Label"},
    )
    entry.add_to_hass(hass)

    assert await async_migrate_entry(hass, entry) is True
    assert entry.data[CONF_IGNORE_LABEL] == data_label.label_id
    assert entry.options[CONF_IGNORE_LABEL] == options_label.label_id
