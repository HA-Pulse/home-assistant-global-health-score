"""Disk threshold tests for the hardware pillar.

Thresholds under test (coordinator._async_calc_hardware):
  sd-card / emmc: critical below 3 GB free (disk score 0), warning below
                  5 GB free (disk score 50)
  ssd:            below 10 % free, disk score scales with free percentage
"""

from __future__ import annotations

import pytest

from custom_components.haghs import coordinator as coordinator_module
from tests.factories import GB, make_coordinator, patch_disk, patch_psi

NEUTRAL_PSI = {"cpu": 1.0, "memory": 1.0, "io": 1.0}


@pytest.mark.parametrize("storage_type", ["sd-card", "emmc"])
async def test_sd_like_storage_is_healthy_above_5gb(hass, storage_type) -> None:
    coord = make_coordinator(hass, options={"storage_type": storage_type})
    with patch_psi(**NEUTRAL_PSI), patch_disk(total=500 * GB, free=100 * GB, percent=20.0):
        result = await coord._async_calc_hardware()
    assert result.hardware_score == pytest.approx(100.0)


@pytest.mark.parametrize("storage_type", ["sd-card", "emmc"])
async def test_sd_like_storage_warns_below_5gb(hass, storage_type) -> None:
    coord = make_coordinator(hass, options={"storage_type": storage_type})
    with patch_psi(**NEUTRAL_PSI), patch_disk(total=500 * GB, free=4 * GB, percent=0.8):
        result = await coord._async_calc_hardware()
    assert result.hardware_score == pytest.approx(87.5)


async def test_sd_like_storage_zero_score_below_3gb(hass) -> None:
    coord = make_coordinator(hass, options={"storage_type": "sd-card"})
    with patch_psi(**NEUTRAL_PSI), patch_disk(total=500 * GB, free=2 * GB, percent=0.4):
        result = await coord._async_calc_hardware()
    assert result.hardware_score == pytest.approx(75.0)


async def test_ssd_is_healthy_at_ten_percent_free(hass) -> None:
    coord = make_coordinator(hass, options={"storage_type": "ssd"})
    with patch_psi(**NEUTRAL_PSI), patch_disk(total=100 * GB, free=10 * GB, percent=90.0):
        result = await coord._async_calc_hardware()
    assert result.hardware_score == pytest.approx(100.0)


async def test_ssd_scales_with_free_percentage(hass) -> None:
    coord = make_coordinator(hass, options={"storage_type": "ssd"})
    with patch_psi(**NEUTRAL_PSI), patch_disk(total=100 * GB, free=5 * GB, percent=95.0):
        result = await coord._async_calc_hardware()
    assert result.hardware_score == pytest.approx(87.5)


async def test_ssd_almost_full_is_heavily_penalised(hass) -> None:
    coord = make_coordinator(hass, options={"storage_type": "ssd"})
    with patch_psi(**NEUTRAL_PSI), patch_disk(total=100 * GB, free=1 * GB, percent=99.0):
        result = await coord._async_calc_hardware()
    assert result.hardware_score == pytest.approx(77.5)


async def test_disk_usage_failure_is_neutral(hass, monkeypatch) -> None:
    coord = make_coordinator(hass)

    def _broken_disk_usage(_path: str):
        raise OSError("no such device")

    monkeypatch.setattr(coordinator_module.psutil, "disk_usage", _broken_disk_usage)
    with patch_psi(**NEUTRAL_PSI):
        result = await coord._async_calc_hardware()
    assert result.hardware_score == pytest.approx(100.0)
    assert result.disk_total == 0
    assert result.disk_free == 0
