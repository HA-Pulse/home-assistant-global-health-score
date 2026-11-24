"""The repairs fix flow never fails on an unknown issue id or on missing issue data (HAGHS-20261124-004)."""

from __future__ import annotations

import pytest
from homeassistant.components.repairs import ConfirmRepairFlow
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import issue_registry as ir
from homeassistant.setup import async_setup_component

from custom_components.haghs.const import DOMAIN, IssueIds
from custom_components.haghs.repairs import async_create_fix_flow

STALE = "issue_from_another_haghs_version"


async def test_an_unknown_issue_id_gets_a_confirm_flow(hass) -> None:
    flow = await async_create_fix_flow(hass, STALE, None)
    assert isinstance(flow, ConfirmRepairFlow)


async def test_an_unknown_haghs_issue_can_be_confirmed_and_disappears(hass) -> None:
    assert await async_setup_component(hass, "repairs", {})
    hass.config.components.add(DOMAIN)
    ir.async_create_issue(
        hass,
        DOMAIN,
        STALE,
        is_fixable=True,
        is_persistent=False,
        severity=ir.IssueSeverity.WARNING,
        translation_key=STALE,
    )
    manager = hass.data["repairs"]["flow_manager"]
    form = await manager.async_init(DOMAIN, context={"issue_id": STALE}, data={"issue_id": STALE})
    assert form["type"] == FlowResultType.FORM
    done = await manager.async_configure(form["flow_id"], {})
    assert done["type"] == FlowResultType.CREATE_ENTRY
    assert ir.async_get(hass).async_get_issue(DOMAIN, STALE) is None


@pytest.mark.parametrize(
    "data", [None, {}, {"entry_id": 42}], ids=["no_data", "empty", "entry_id_not_a_string"]
)
async def test_fallback_missing_without_usable_data_aborts(hass, data) -> None:
    flow = await async_create_fix_flow(hass, IssueIds.FALLBACK_MISSING, data)
    flow.hass = hass
    result = await flow.async_step_init()
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "config_entry_missing"
