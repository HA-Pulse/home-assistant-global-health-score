"""HAGHS coordinator."""

from __future__ import annotations

import asyncio
import fnmatch
import logging
import math
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

import psutil
from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.const import (
    EVENT_HOMEASSISTANT_STARTED,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.core import CoreState, Event, HomeAssistant, callback
from homeassistant.helpers import (
    device_registry as dr,
)
from homeassistant.helpers import (
    entity_registry as er,
)
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import (
    ATTR_UNREGISTERED_PREFIX,
    CONF_BATTERY_GRACE_MINUTES,
    CONF_CPU_SENSOR,
    CONF_DB_SENSOR,
    CONF_IGNORE_LABELS,
    CONF_IGNORE_PATTERNS,
    CONF_RAM_SENSOR,
    CONF_STORAGE_TYPE,
    CONF_UPDATE_INTERVAL,
    CONF_ZOMBIE_GRACE_MINUTES,
    DATA_BOOT_TIME,
    DATA_UPDATE_FIRST_SEEN,
    DEFAULT_BATTERY_GRACE_MINUTES,
    DEFAULT_STORAGE_TYPE,
    DEFAULT_UPDATE_INTERVAL,
    DEFAULT_ZOMBIE_GRACE_MINUTES,
    DOMAIN,
    REC_ALL_CLEAR,
    REC_BACKUP_STALE,
    REC_CORE_LAG,
    REC_CPU_LOAD_CLASSIC,
    REC_CPU_LOAD_PSI,
    REC_DB_OVER_LIMIT,
    REC_DISK_SD_LOW,
    REC_DISK_SSD_LOW,
    REC_IO_PRESSURE,
    REC_POWER_UNSTABLE,
    REC_RAM_PRESSURE_CLASSIC,
    REC_RAM_PRESSURE_PSI,
    REC_UPDATES_PENDING,
    REC_ZOMBIES,
    UPDATE_GRACE_DAYS,
    ZOMBIE_LIST_CAP,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[str] = ["sensor"]

# Size constants
_GB = 1024**3

# Timeout for each scoring sub-calculation (seconds).
PILLAR_TIMEOUT: float = 10.0

# Default HA SQLite database filename
HA_DB_NAME = "home-assistant_v2.db"

# PSI (Pressure Stall Information) paths — Linux only
PSI_CPU_PATH = "/proc/pressure/cpu"
PSI_MEMORY_PATH = "/proc/pressure/memory"
PSI_IO_PATH = "/proc/pressure/io"

# Regex to extract 'some avg10=X.XX' from PSI files
_PSI_SOME_AVG10_RE = re.compile(r"some\s+avg10=(\d+\.?\d*)")

# Domains to check for zombie entities.
#
# Selection rule: any domain whose entities represent a physical device or
# integration channel whose `unavailable` / `unknown` state signals a real
# health problem. Helpers (input_*, counter, timer), user-defined logic
# (automation, script, scene), HA-internal entities (person, zone, sun) and
# domains whose default state is `unknown` until first interaction (button,
# event) are intentionally excluded so they cannot trigger false positives.
ZOMBIE_DOMAINS: frozenset[str] = frozenset(
    [
        "alarm_control_panel",
        "binary_sensor",
        "camera",
        "climate",
        "cover",
        "device_tracker",
        "fan",
        "humidifier",
        "lawn_mower",
        "light",
        "lock",
        "media_player",
        "number",
        "remote",
        "select",
        "sensor",
        "siren",
        "switch",
        "text",
        "vacuum",
        "valve",
        "water_heater",
    ]
)


@dataclass
class _PsiData:
    """Pressure Stall Information (some avg10 values).

    None means the file could not be read (unsupported platform / old kernel).
    """

    cpu: float | None = None
    memory: float | None = None
    io: float | None = None

    @property
    def available(self) -> bool:
        """Return True if at least CPU and memory PSI data was read."""
        return self.cpu is not None and self.memory is not None


@dataclass
class _HardwareResult:
    """Result of the hardware pillar calculation."""

    hardware_score: float = 100.0
    cpu: float = 0.0
    ram: float = 0.0
    io: float = 0.0
    disk: float = 0.0
    disk_total: int = 0
    disk_free: int = 0
    p_cpu: int = 0
    p_ram: int = 0
    p_io: int = 0
    p_power: int = 0
    psi_available: bool = False
    cpu_used_psi: bool = False
    ram_used_psi: bool = False


@dataclass
class _ApplicationResult:
    """Result of the application pillar calculation."""

    app_score: int = 100
    zombie_count: int = 0
    zombie_list: list[str] = field(default_factory=list)
    zombie_per_domain: dict[str, int] = field(default_factory=dict)
    db_mb: float = 0.0
    db_limit_mb: float = 1000.0
    update_count: int = 0
    pending_updates: list[str] = field(default_factory=list)
    config_bonus: int = 0
    p_backup: int = 0
    p_core_lag: int = 0
    p_zombie: int = 0


@dataclass
class _RecorderInfo:
    """Recorder configuration data — prepared for Phase 3 scoring."""

    keep_days: int | None = None
    entity_filter_active: bool = False
    available: bool = False


def _compile_patterns(raw: list[str] | None) -> list[re.Pattern[str]]:
    """Translate user-supplied glob patterns to compiled regex objects.

    Invalid patterns are dropped with a warning rather than raising — a single
    typo must not break zombie or update detection for the whole instance.
    """
    if not raw:
        return []
    compiled: list[re.Pattern[str]] = []
    for pattern in raw:
        if not pattern:
            continue
        try:
            compiled.append(re.compile(fnmatch.translate(pattern)))
        except re.error as err:
            # Defense-in-depth: fnmatch.translate escapes most malformed
            # glob input (e.g. unclosed character classes) so re.compile
            # rarely raises in practice, but we keep the guard in case
            # CPython's translation rules change in a future release.
            _LOGGER.warning(
                "HAGHS: Invalid ignore pattern %r (%s) — skipping",
                pattern,
                err,
            )
    return compiled


class HaghsDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator that calculates the Global Health Score."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the coordinator."""
        # Options take priority over data for runtime-configurable fields
        opts: dict = {**entry.data, **entry.options}

        interval_sec = int(opts.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL))
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=interval_sec),
        )
        self.cpu_id: str | None = opts.get(CONF_CPU_SENSOR)
        self.ram_id: str | None = opts.get(CONF_RAM_SENSOR)
        self.db_sensor_id: str | None = opts.get(CONF_DB_SENSOR) or None
        self.ignore_labels: list[str] = list(opts.get(CONF_IGNORE_LABELS) or [])
        self._ignore_patterns: list[re.Pattern[str]] = _compile_patterns(
            opts.get(CONF_IGNORE_PATTERNS)
        )
        self._storage_type: str = opts.get(CONF_STORAGE_TYPE, DEFAULT_STORAGE_TYPE)

        # Grace windows are user-configurable in the Options Flow. Both
        # values are stored in minutes for friendlier UX, multiplied to
        # seconds here once at init so the hot path stays cheap.
        self._zombie_grace_seconds: int = (
            int(opts.get(CONF_ZOMBIE_GRACE_MINUTES, DEFAULT_ZOMBIE_GRACE_MINUTES)) * 60
        )
        self._battery_grace_seconds: int = (
            int(opts.get(CONF_BATTERY_GRACE_MINUTES, DEFAULT_BATTERY_GRACE_MINUTES)) * 60
        )

        # Paths for auto-detection (resolved once at init)
        self._db_path: str = hass.config.path(HA_DB_NAME)
        self._config_dir: str = hass.config.config_dir

        # Recorder info — populated on each update cycle (Phase 3 ready)
        self.recorder_info: _RecorderInfo = _RecorderInfo()

        # Boot-time baseline for zombie grace. Stored in hass.data so it
        # survives integration reloads and reflects the actual HA boot rather
        # than the latest reload. setdefault preserves an existing value.
        hass_data = hass.data.setdefault(DOMAIN, {})
        self._boot_time = hass_data.setdefault(DATA_BOOT_TIME, dt_util.utcnow())

        # First-seen timestamps for pending update entities (#26). Stored in
        # hass.data so they survive integration reloads. Reset on HA restart,
        # which is desired: a fresh boot effectively gives all current updates
        # a new grace window.
        self._update_first_seen: dict[str, datetime] = hass_data.setdefault(
            DATA_UPDATE_FIRST_SEEN, {}
        )

        # Track ghost zombies (no entity-registry entry) so we warn at most
        # once per entity per coordinator instance instead of every refresh.
        self._logged_ghost_entities: set[str] = set()

        # Registry-race guard: if HAGHS first runs while HA is still in the
        # 'starting' state, the entity registry (and therefore label
        # assignments) may not yet be loaded from storage, which would cause
        # labelled-but-unavailable entities to be misreported as zombies on
        # the first refresh after boot.
        #
        # Use `state == CoreState.running` instead of `hass.is_running`, which
        # returns True for both `starting` and `running` and would defeat the
        # deferral during the startup window we actually care about (#13).
        self._registries_ready: bool = hass.state == CoreState.running
        if not self._registries_ready:
            hass.bus.async_listen_once(
                EVENT_HOMEASSISTANT_STARTED,
                self._async_registries_ready,
            )

    @callback
    def _async_registries_ready(self, _event: Event) -> None:
        """Mark registries as loaded once HA finishes startup."""
        self._registries_ready = True

    def _is_ignored(
        self,
        entity_id: str,
        entity_entry: er.RegistryEntry | None,
    ) -> bool:
        """Return True if an entity should be excluded from health checks.

        Four exclusion sources, checked in cheapest-first order:
          1. Disabled in the entity registry (user clicked "Disable entity"
             or the integration disabled it). Clear user-intent signal that
             takes precedence over the other checks.
          2. Glob patterns on entity_id (no registry lookup required)
          3. Any of the configured ignore labels on the entity's registry entry
          4. Any of the configured ignore labels on the entity's device

        Note: ``hidden_by`` is intentionally not treated as ignore. Hidden
        entities are still functional; the user only hid them from
        auto-generated dashboards. To exclude them from HAGHS the user
        should disable the entity or apply one of the ignore labels.

        Multiple ignore labels can be configured. Toggling them on/off at
        runtime is done via Home Assistant's native ``label.assign`` and
        ``label.remove`` service actions, not via a HAGHS-specific service.
        """
        if entity_entry is not None and entity_entry.disabled_by is not None:
            return True

        if self._ignore_patterns and any(p.match(entity_id) for p in self._ignore_patterns):
            return True

        if not self.ignore_labels or entity_entry is None:
            return False

        entity_labels = entity_entry.labels or set()
        if any(label in entity_labels for label in self.ignore_labels):
            return True

        if entity_entry.device_id:
            dev_reg = dr.async_get(self.hass)
            device_entry = dev_reg.async_get(entity_entry.device_id)
            if device_entry:
                device_labels = device_entry.labels or set()
                if any(label in device_labels for label in self.ignore_labels):
                    return True

        return False

    # ------------------------------------------------------------------
    # Main update — orchestrates sub-calculations with safety net
    # ------------------------------------------------------------------

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data and calculate the health score.

        Each pillar runs in its own guarded coroutine.  On timeout or
        exception the affected pillar falls back to a neutral score
        (100 / no penalty) and a warning is logged.  The coordinator
        itself never crashes.
        """
        # Recorder info — read before app pillar so config audit can use it
        self.recorder_info = self._read_recorder_info()

        hw = await self._safe_calc(
            "hardware",
            self._async_calc_hardware(),
            _HardwareResult(),
        )

        app = await self._safe_calc(
            "application",
            self._async_calc_application(),
            _ApplicationResult(),
        )

        global_score = max(
            0, min(100, math.floor((hw.hardware_score * 0.4) + (app.app_score * 0.6)))
        )

        advice = self._build_recommendations(hw, app)
        rec_flags = self._build_rec_flags(hw, app)

        return {
            "global_score": int(global_score),
            "hardware_score": int(hw.hardware_score),
            "application_score": app.app_score,
            "zombie_count": app.zombie_count,
            "zombie_entities": app.zombie_list,
            "zombie_count_per_domain": app.zombie_per_domain,
            "db_size_mb": round(app.db_mb, 1),
            "psi_available": hw.psi_available,
            "recorder_keep_days": self.recorder_info.keep_days,
            "recorder_filter_active": self.recorder_info.entity_filter_active,
            "pending_updates": app.pending_updates,
            "recommendations": ("\n".join(advice) if advice else REC_ALL_CLEAR),
            **rec_flags,
        }

    async def _safe_calc(
        self,
        name: str,
        coro: Any,
        fallback: Any,
    ) -> Any:
        """Run *coro* with a timeout; return *fallback* on any failure."""
        try:
            return await asyncio.wait_for(coro, timeout=PILLAR_TIMEOUT)
        except TimeoutError:
            _LOGGER.warning(
                "HAGHS: %s calculation timed out after %ss — using neutral score",
                name,
                PILLAR_TIMEOUT,
            )
            return fallback
        except Exception:
            _LOGGER.warning(
                "HAGHS: %s calculation failed — using neutral score",
                name,
                exc_info=True,
            )
            return fallback

    # ------------------------------------------------------------------
    # PSI (Pressure Stall Information) reader
    # ------------------------------------------------------------------

    async def _async_read_psi(self) -> _PsiData:
        """Read Linux PSI data from /proc/pressure via executor.

        Returns _PsiData with None fields for any file that cannot be read
        (Windows, old kernels, containers without /proc mounted).
        """
        return await self.hass.async_add_executor_job(self._read_psi_sync)

    @staticmethod
    def _read_psi_sync() -> _PsiData:
        """Synchronous PSI reader — runs in the executor thread pool."""
        return _PsiData(
            cpu=HaghsDataUpdateCoordinator._parse_psi_file(PSI_CPU_PATH),
            memory=HaghsDataUpdateCoordinator._parse_psi_file(PSI_MEMORY_PATH),
            io=HaghsDataUpdateCoordinator._parse_psi_file(PSI_IO_PATH),
        )

    @staticmethod
    def _parse_psi_file(path: str) -> float | None:
        """Parse 'some avg10' from a single PSI file.  Returns None on failure."""
        try:
            with open(path, encoding="utf-8") as fh:
                content = fh.read()
            match = _PSI_SOME_AVG10_RE.search(content)
            if match:
                return float(match.group(1))
            return None
        except (OSError, ValueError):
            return None

    # ------------------------------------------------------------------
    # Hardware pillar (40 %)
    # ------------------------------------------------------------------

    async def _async_calc_hardware(self) -> _HardwareResult:
        """Calculate the hardware pillar score.

        Data sources — with smart fallback:
          CPU:  PSI /proc/pressure/cpu some avg10  → fallback: CONF_CPU_SENSOR
          RAM:  PSI /proc/pressure/memory some avg10  → fallback: CONF_RAM_SENSOR
          I/O:  PSI /proc/pressure/io some avg10  (PSI-only, no fallback)
          Disk: psutil.disk_usage (always auto-detected)

        PSI values measure stall time (% of time tasks waited for a resource).
        Classic sensor values measure utilization (% of resource in use).
        These require separate threshold tiers because their scales differ
        fundamentally.
        """
        # Try PSI first (non-blocking via executor)
        psi = await self._async_read_psi()
        use_psi = psi.available

        # -- CPU --
        if psi.cpu is not None:
            cpu = psi.cpu
            p_cpu = self._psi_cpu_penalty(cpu)
        else:
            cpu = self._get_float(self.cpu_id)
            if cpu > 100:
                _LOGGER.warning(
                    "HAGHS: CPU sensor '%s' returned %.1f — expected 0-100%%. "
                    "Please select a sensor that reports CPU usage in percent",
                    self.cpu_id,
                    cpu,
                )
                cpu = min(cpu, 100.0)
            p_cpu = self._classic_cpu_penalty(cpu)
        score_cpu = 100 - p_cpu

        # -- RAM --
        if psi.memory is not None:
            ram = psi.memory
            p_ram = self._psi_memory_penalty(ram)
        else:
            ram = self._get_float(self.ram_id)
            if ram > 100:
                _LOGGER.warning(
                    "HAGHS: RAM sensor '%s' returned %.1f — expected 0-100%%. "
                    "Please select a sensor that reports memory usage in percent",
                    self.ram_id,
                    ram,
                )
                ram = min(ram, 100.0)
            p_ram = self._classic_ram_penalty(ram)
        score_ram = 100 - p_ram

        # -- I/O (PSI-only — no classic fallback) --
        io_val = psi.io if psi.io is not None else 0.0
        p_io = 0
        if psi.io is not None:
            p_io = self._psi_io_penalty(psi.io)
        score_io = 100 - p_io

        # -- Disk: always auto-detected via psutil — smart thresholds --
        disk_usage = await self._async_get_disk_usage()
        if disk_usage is not None:
            disk_total = disk_usage.total
            disk_free = disk_usage.free
            disk_pct = disk_usage.percent

            if self._storage_type in ("sd-card", "emmc"):
                # SD-Card / eMMC logic: critical < 3 GB free, warning < 5 GB free
                if disk_free < 3 * _GB:
                    score_disk = 0.0
                elif disk_free < 5 * _GB:
                    score_disk = 50.0
                else:
                    score_disk = 100.0
            else:
                # SSD logic: warning < 10% free
                free_pct = (disk_free / disk_total) * 100 if disk_total > 0 else 100
                if free_pct < 10:
                    score_disk = max(0.0, free_pct * 10)
                else:
                    score_disk = 100.0
        else:
            disk_total = 0
            disk_free = 0
            disk_pct = 0.0
            score_disk = 100.0

        # -- Power Supply (RPi auto-detection) --
        p_power = 0
        power_state = self.hass.states.get("binary_sensor.rpi_power_status")
        if power_state and power_state.state == "on":
            p_power = 20

        # -- Final hardware score --
        # When PSI I/O is available: 4 components (CPU, RAM, I/O, Disk)
        # When I/O is not available: 3 components (CPU, RAM, Disk)
        # Power penalty is applied as a flat deduction (not averaged)
        if psi.io is not None:
            hardware_final = max(
                0.0,
                min(100.0, (score_cpu + score_ram + score_io + score_disk) / 4 - p_power),
            )
        else:
            hardware_final = max(
                0.0,
                min(100.0, (score_cpu + score_ram + score_disk) / 3 - p_power),
            )

        if use_psi:
            _LOGGER.debug(
                "HAGHS: Using PSI data — cpu=%.2f memory=%.2f io=%s",
                psi.cpu,
                psi.memory,
                psi.io,
            )
        else:
            _LOGGER.debug("HAGHS: PSI not available — using sensor fallback")

        return _HardwareResult(
            hardware_score=hardware_final,
            cpu=cpu,
            ram=ram,
            io=io_val,
            disk=disk_pct,
            disk_total=disk_total,
            disk_free=disk_free,
            p_cpu=p_cpu,
            p_ram=p_ram,
            p_io=p_io,
            p_power=p_power,
            psi_available=use_psi,
            cpu_used_psi=psi.cpu is not None,
            ram_used_psi=psi.memory is not None,
        )

    # -- CPU penalty tiers -------------------------------------------------

    @staticmethod
    def _classic_cpu_penalty(cpu: float) -> int:
        """Tiered penalty for classic CPU usage sensor (utilization %).

        Classic sensors report how busy the CPU is.  25% is normal for an
        active system, so penalties only start above that threshold.
        """
        if cpu <= 25:
            return 0
        if cpu <= 40:
            return 10
        if cpu <= 60:
            return 25
        if cpu <= 80:
            return 50
        return 80

    @staticmethod
    def _psi_cpu_penalty(psi_val: float) -> int:
        """Tiered penalty for PSI CPU pressure (stall time %).

        PSI measures how long tasks waited for CPU.  Even 5% stall time
        is noticeable — automation latency increases measurably.
        """
        if psi_val <= 5:
            return 0
        if psi_val <= 15:
            return 10
        if psi_val <= 30:
            return 25
        if psi_val <= 50:
            return 50
        return 80

    # -- RAM penalty tiers -------------------------------------------------

    @staticmethod
    def _classic_ram_penalty(ram: float) -> int:
        """Tiered penalty for classic RAM usage sensor (utilization %).

        HA + Supervisor typically consume 60-70% of RAM.  Penalties start
        at 70% with a linear ramp to leave headroom for spikes.
        """
        if ram < 70:
            return 0
        if ram < 80:
            return int((ram - 70) * 3.33)  # 0 → 33
        if ram < 90:
            return int(33 + (ram - 80) * 3.37)  # 33 → 67
        return 80

    @staticmethod
    def _psi_memory_penalty(psi_val: float) -> int:
        """Tiered penalty for PSI memory pressure (stall time %).

        Memory stalls are more critical than CPU stalls because they can
        trigger the OOM killer.  Thresholds are tighter than CPU.
        """
        if psi_val <= 5:
            return 0
        if psi_val <= 10:
            return 10
        if psi_val <= 25:
            return 25
        if psi_val <= 40:
            return 50
        return 80

    # -- I/O penalty tiers -------------------------------------------------

    @staticmethod
    def _psi_io_penalty(psi_val: float) -> int:
        """Tiered penalty for PSI I/O pressure (stall time %).

        I/O stalls directly affect recorder writes, automation execution,
        and restart times.  Thresholds match CPU PSI.
        """
        if psi_val <= 5:
            return 0
        if psi_val <= 15:
            return 10
        if psi_val <= 30:
            return 25
        if psi_val <= 50:
            return 50
        return 80

    async def _async_get_disk_usage(self) -> Any | None:
        """Return full psutil disk_usage result, or None on failure."""
        try:
            return await self.hass.async_add_executor_job(psutil.disk_usage, self._config_dir)
        except (OSError, FileNotFoundError):
            _LOGGER.warning(
                "HAGHS: Could not read disk usage for %s — assuming healthy",
                self._config_dir,
            )
            return None

    # ------------------------------------------------------------------
    # Application pillar (60 %)
    # ------------------------------------------------------------------

    async def _async_calc_application(self) -> _ApplicationResult:
        """Calculate the application pillar score."""
        # A. ZOMBIES
        zombie_list, p_zombie, zombie_count, zombie_per_domain = self._calc_zombies()

        # B. INTEGRATION HEALTH
        p_integration = self._calc_integration_health()

        # C. MAINTENANCE — DB size auto-detected (blocking I/O → executor)
        db_mb, p_db, db_limit_mb = await self._async_calc_maintenance()

        # D. UPDATES
        p_backup, update_count, p_updates, p_core_lag, pending_updates = self._calc_updates()

        # E. CONFIG AUDIT — bonus for good recorder configuration
        config_bonus = self._calc_config_audit()

        app_final = max(
            0,
            min(
                100,
                100 - p_zombie - p_integration - p_backup - p_updates - p_db + config_bonus,
            ),
        )

        # Hard cap: a perfect 100 must always reflect zero detected issues.
        # On large instances the ratio-based p_zombie can be small enough
        # that config_bonus fully offsets it, which would otherwise hide
        # existing zombies behind a 100 score.
        if zombie_count > 0:
            app_final = min(99, app_final)

        return _ApplicationResult(
            app_score=app_final,
            zombie_count=zombie_count,
            zombie_list=zombie_list,
            zombie_per_domain=zombie_per_domain,
            db_mb=db_mb,
            db_limit_mb=db_limit_mb,
            update_count=update_count,
            pending_updates=pending_updates,
            config_bonus=config_bonus,
            p_backup=p_backup,
            p_core_lag=p_core_lag,
            p_zombie=p_zombie,
        )

    # ------------------------------------------------------------------
    # Application sub-calculations
    # ------------------------------------------------------------------

    def _calc_zombies(self) -> tuple[list[str], int, int, dict[str, int]]:
        """Detect zombie entities, respecting ignore labels and grace period.

        Returns (zombie_list_capped, p_zombie, zombie_count, per_domain).
        zombie_list is capped to ZOMBIE_LIST_CAP entries because the HA
        state machine caps an attribute payload at 16 KB; zombie_count and
        the per_domain dict always reflect the full count so users can see
        the true scope even when the listing is truncated.
        """
        # Defer detection until HA is fully running. Otherwise the entity
        # registry may not yet be loaded from storage and ignore labels would
        # be missing, producing false positives right after boot (#13).
        if not self._registries_ready:
            _LOGGER.debug("HAGHS: HA still starting up — deferring zombie detection")
            return [], 0, 0, {}

        ent_reg = er.async_get(self.hass)
        now = dt_util.utcnow()
        zombie_list: list[str] = []
        zombie_per_domain: dict[str, int] = {}
        # Denominator only counts entities that could ever be flagged as zombies,
        # so an instance with many automations/scripts/etc. is not artificially
        # diluted. Counted in the same pass as detection.
        zombie_domain_total = 0

        for state in self.hass.states.async_all():
            if state.domain not in ZOMBIE_DOMAINS:
                continue
            zombie_domain_total += 1
            if state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                continue

            # Grace period: skip entities that changed less than the window
            # ago. last_changed values older than the recorded boot time were
            # restored from the recorder and are not a reliable baseline, so
            # treat boot time as the floor. Battery-class entities use a
            # separate, typically longer window (configurable in the Options
            # Flow, defaults are 15 min for general and 60 min for battery).
            effective_seen = max(state.last_changed, self._boot_time)
            grace_seconds = (
                self._battery_grace_seconds
                if state.attributes.get("device_class") == "battery"
                else self._zombie_grace_seconds
            )
            if (now - effective_seen).total_seconds() < grace_seconds:
                continue

            entity_id = state.entity_id
            if "integration_health" in entity_id:
                continue

            entity_entry = ent_reg.async_get(entity_id)
            if self._is_ignored(entity_id, entity_entry):
                continue

            zombie_per_domain[state.domain] = zombie_per_domain.get(state.domain, 0) + 1

            if entity_entry is None:
                # Ghost zombie: exists in the state machine but has no entity
                # registry entry, so it cannot be managed in the HA UI.
                # Surface it explicitly and warn once per id (#6).
                if entity_id not in self._logged_ghost_entities:
                    _LOGGER.warning(
                        "HAGHS: Detected unregistered zombie entity '%s'. "
                        "It exists in the state machine but has no entity "
                        "registry entry, so it cannot be managed via the "
                        "HA UI. Check the integration that created it.",
                        entity_id,
                    )
                    self._logged_ghost_entities.add(entity_id)
                zombie_list.append(f"{ATTR_UNREGISTERED_PREFIX}{entity_id}")
            else:
                zombie_list.append(entity_id)

        zombie_count = len(zombie_list)

        # Ratio-based penalty: percentage of zombies relative to entities in
        # ZOMBIE_DOMAINS only. Factor 7 + ceil ensures zombies are visible on
        # all instance sizes.
        if zombie_domain_total > 0:
            zombie_ratio_pct = (zombie_count / zombie_domain_total) * 100
            p_zombie = min(20, math.ceil(zombie_ratio_pct * 7))
        else:
            p_zombie = 0

        # Cap the list for state attributes (count + per_domain stay full).
        return zombie_list[:ZOMBIE_LIST_CAP], p_zombie, zombie_count, zombie_per_domain

    def _calc_integration_health(self) -> int:
        """Count unhealthy integrations via native ConfigEntry states.

        Checks for integrations stuck in SETUP_ERROR, SETUP_RETRY, or
        FAILED_UNLOAD — the same states HA shows as "error" in the UI.
        Penalty: 5 pts per unhealthy integration, capped at 15.
        """
        unhealthy_states = {
            ConfigEntryState.SETUP_ERROR,
            ConfigEntryState.SETUP_RETRY,
            ConfigEntryState.FAILED_UNLOAD,
        }
        failed = sum(
            1
            for entry in self.hass.config_entries.async_entries()
            if entry.state in unhealthy_states
        )
        return min(15, failed * 5)

    async def _async_calc_maintenance(self) -> tuple[float, int, float]:
        """Calculate DB penalty with dynamic limit based on entity count."""
        db_mb = await self._async_get_db_size_mb()
        total_entities = len(self.hass.states.async_all())
        db_limit_mb = 1000 + (total_entities * 2.5)

        p_db = 0
        if db_mb < db_limit_mb:
            p_db = 0
        elif db_mb < db_limit_mb * 2.5:
            p_db = 10
        else:
            p_db = 30

        return db_mb, p_db, db_limit_mb

    async def _async_get_db_size_mb(self) -> float:
        """Return the HA database size in MB.

        If an external DB sensor is configured, its state is used directly
        (expected to report size in MB).  Otherwise falls back to measuring
        the local SQLite file via os.path.getsize.
        Returns 0.0 if no measurement is available (external DB without
        sensor, or missing SQLite file).
        """
        # External DB sensor override
        if self.db_sensor_id:
            val = self._get_float(self.db_sensor_id)
            if val > 0:
                _LOGGER.debug(
                    "HAGHS: Using external DB sensor '%s' — %.1f MB",
                    self.db_sensor_id,
                    val,
                )
                return val
            _LOGGER.debug(
                "HAGHS: External DB sensor '%s' returned %.1f — skipping DB penalty",
                self.db_sensor_id,
                val,
            )
            return 0.0

        # Default: local SQLite file
        try:
            size_bytes: int = await self.hass.async_add_executor_job(os.path.getsize, self._db_path)
            return size_bytes / (1024 * 1024)
        except OSError:
            _LOGGER.debug(
                "HAGHS: SQLite DB not found at %s — assuming external database",
                self._db_path,
            )
            return 0.0

    def _calc_updates(self) -> tuple[int, int, int, int, list[str]]:
        """Calculate backup, update and core-lag penalties.

        Returns (p_backup, update_count, p_updates, p_core_lag, pending_updates).
        Update entities with the ignore label or matching an ignore pattern
        are excluded from counting and penalties. Pending updates appear in
        pending_updates immediately but only contribute to update_count after
        UPDATE_GRACE_DAYS (#26). Core lag threshold: >= 3 months behind.
        """
        backup_state = self.hass.states.get("binary_sensor.backups_stale")
        p_backup = 30 if (backup_state and backup_state.state == "on") else 0

        ent_reg = er.async_get(self.hass)
        now = dt_util.utcnow()
        grace = timedelta(days=UPDATE_GRACE_DAYS)
        update_count = 0
        pending_updates: list[str] = []
        currently_pending: set[str] = set()

        for state in self.hass.states.async_all():
            if state.domain != "update" or state.state != "on":
                continue
            entity_entry = ent_reg.async_get(state.entity_id)
            if self._is_ignored(state.entity_id, entity_entry):
                continue

            currently_pending.add(state.entity_id)
            first_seen = self._update_first_seen.setdefault(state.entity_id, now)
            name = state.attributes.get("friendly_name", state.entity_id)
            pending_updates.append(name)
            if now - first_seen >= grace:
                update_count += 1

        # Prune entries for updates that are no longer pending so installed
        # updates don't keep a stale timestamp around.
        for stale_id in list(self._update_first_seen):
            if stale_id not in currently_pending:
                del self._update_first_seen[stale_id]

        p_core_lag = 0
        core_entity_id = self._detect_core_update_entity()
        core_state = self.hass.states.get(core_entity_id) if core_entity_id else None
        if core_state:
            current: str | None = core_state.attributes.get("installed_version")
            latest: str | None = core_state.attributes.get("latest_version")
            if current and latest and "." in current and "." in latest:
                try:
                    cur_parts = [int(x) for x in current.split(".")[:2]]
                    lat_parts = [int(x) for x in latest.split(".")[:2]]
                    if ((lat_parts[0] * 12) + lat_parts[1]) - (
                        (cur_parts[0] * 12) + cur_parts[1]
                    ) >= 3:
                        p_core_lag = 20
                except (ValueError, IndexError):
                    pass

        p_updates = min(35, (update_count * 5) + p_core_lag)
        return p_backup, update_count, p_updates, p_core_lag, pending_updates

    # ------------------------------------------------------------------
    # Config Audit — bonus for good recorder configuration
    # ------------------------------------------------------------------

    def _calc_config_audit(self) -> int:
        """Calculate config audit bonus based on recorder configuration.

        Awards bonus points (reduces net penalty) for good practices:
          +5  if purge_keep_days is configured
          +5  if include/exclude entity filter is active
        Max bonus: 10.
        """
        bonus = 0
        if self.recorder_info.available:
            if self.recorder_info.keep_days is not None:
                bonus += 5
            if self.recorder_info.entity_filter_active:
                bonus += 5
        return bonus

    # ------------------------------------------------------------------
    # Recorder info reader
    # ------------------------------------------------------------------

    def _read_recorder_info(self) -> _RecorderInfo:
        """Read recorder configuration from hass.data.

        Safe access — returns empty _RecorderInfo if recorder is not loaded
        or not available (e.g. external database without recorder component).
        """
        try:
            recorder = self.hass.data.get("recorder_instance")
            if recorder is None:
                _LOGGER.debug("HAGHS: Recorder instance not found in hass.data")
                return _RecorderInfo()

            keep_days = getattr(recorder, "keep_days", None)
            entity_filter = getattr(recorder, "entity_filter", None)

            return _RecorderInfo(
                keep_days=keep_days,
                entity_filter_active=entity_filter is not None,
                available=True,
            )
        except Exception:
            _LOGGER.warning(
                "HAGHS: Failed to read recorder info — skipping",
                exc_info=True,
            )
            return _RecorderInfo()

    # ------------------------------------------------------------------
    # Dynamic core update entity detection
    # ------------------------------------------------------------------

    def _detect_core_update_entity(self) -> str | None:
        """Dynamically find the HA Core update entity.

        Searches the update domain for an entity that represents
        Home Assistant Core.  Works across Supervised, Docker, and K8s setups.

        Detection strategy (first match wins):
          1. entity_id contains 'home_assistant_core'
          2. title attribute contains 'Home Assistant Core' (case-insensitive)
        """
        for state in self.hass.states.async_all("update"):
            eid = state.entity_id
            if "home_assistant_core" in eid:
                return eid
            title = state.attributes.get("title", "")
            if title and "home assistant core" in title.lower():
                return eid
        _LOGGER.debug("HAGHS: No HA Core update entity found — core lag check skipped")
        return None

    # ------------------------------------------------------------------
    # Recommendations builder
    # ------------------------------------------------------------------

    def _build_recommendations(
        self,
        hw: _HardwareResult,
        app: _ApplicationResult,
    ) -> list[str]:
        """Build human-readable recommendation strings.

        All templates are defined in const.py (mirrored in strings.json)
        so translators can find and override them.
        """
        advice: list[str] = []
        if hw.p_cpu > 0:
            cpu_tpl = REC_CPU_LOAD_PSI if hw.cpu_used_psi else REC_CPU_LOAD_CLASSIC
            advice.append(cpu_tpl.format(cpu_pct=hw.cpu))
        if hw.p_ram > 0:
            ram_tpl = REC_RAM_PRESSURE_PSI if hw.ram_used_psi else REC_RAM_PRESSURE_CLASSIC
            advice.append(ram_tpl.format(ram_pct=hw.ram))
        if hw.p_io > 0:
            advice.append(REC_IO_PRESSURE.format(io_pct=hw.io))
        if self._is_disk_low_sd(hw):
            advice.append(
                REC_DISK_SD_LOW.format(
                    free_gb=hw.disk_free / _GB,
                    storage_type=self._storage_type,
                )
            )
        elif self._is_disk_low_ssd(hw):
            advice.append(REC_DISK_SSD_LOW.format(free_gb=hw.disk_free / _GB))
        if app.db_mb > app.db_limit_mb:
            advice.append(
                REC_DB_OVER_LIMIT.format(
                    db_gb=app.db_mb / 1000,
                    limit_gb=app.db_limit_mb / 1000,
                )
            )
        if hw.p_power > 0:
            advice.append(REC_POWER_UNSTABLE)
        if app.p_backup > 0:
            advice.append(REC_BACKUP_STALE)
        if app.update_count > 0:
            advice.append(REC_UPDATES_PENDING.format(count=app.update_count))
        if app.p_zombie > 0:
            advice.append(REC_ZOMBIES.format(count=app.zombie_count))
        if app.p_core_lag > 0:
            advice.append(REC_CORE_LAG)
        return advice

    def _is_disk_low_sd(self, hw: _HardwareResult) -> bool:
        """Return True if the SD-card / eMMC low-disk threshold is met."""
        return (
            self._storage_type in ("sd-card", "emmc")
            and hw.disk_total > 0
            and hw.disk_free < 5 * _GB
        )

    def _is_disk_low_ssd(self, hw: _HardwareResult) -> bool:
        """Return True if the SSD low-disk threshold (<10 % free) is met."""
        if self._storage_type != "ssd" or hw.disk_total <= 0:
            return False
        return (hw.disk_free / hw.disk_total) * 100 < 10

    def _build_rec_flags(
        self,
        hw: _HardwareResult,
        app: _ApplicationResult,
    ) -> dict[str, bool]:
        """Mirror _build_recommendations as a flat dict of boolean attributes.

        Dashboards and external integrations should read these via state_attr
        instead of parsing the rendered recommendations string. Keep the keys
        in sync with REC_FLAG_KEYS in const.py.
        """
        return {
            "rec_cpu_load": hw.p_cpu > 0,
            "rec_ram_pressure": hw.p_ram > 0,
            "rec_io_pressure": hw.p_io > 0,
            "rec_disk_low": self._is_disk_low_sd(hw) or self._is_disk_low_ssd(hw),
            "rec_db_over_limit": app.db_mb > app.db_limit_mb,
            "rec_power_unstable": hw.p_power > 0,
            "rec_backup_stale": app.p_backup > 0,
            "rec_updates_pending": app.update_count > 0,
            "rec_zombie": app.zombie_count > 0,
            "rec_core_lag": app.p_core_lag > 0,
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_float(self, entity_id: str | None) -> float:
        """Safely read a float value from an entity state."""
        if not entity_id:
            return 0.0
        state = self.hass.states.get(entity_id)
        if not state or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return 0.0
        try:
            return float(state.state)
        except (ValueError, TypeError):
            return 0.0
