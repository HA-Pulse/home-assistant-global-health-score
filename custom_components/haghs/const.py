"""Constants for the HAGHS integration."""

from dataclasses import dataclass
from enum import StrEnum

DOMAIN = "haghs"

# Config Keys
CONF_CPU_SENSOR = "cpu_sensor"
CONF_RAM_SENSOR = "ram_sensor"
CONF_DB_SENSOR = "db_sensor"
# CONF_IGNORE_LABEL is deprecated since v3.4 — kept here for the migration
# step that converts the legacy single label into CONF_IGNORE_LABELS.
CONF_IGNORE_LABEL = "ignore_label"
CONF_IGNORE_LABELS = "ignore_labels"
CONF_IGNORE_PATTERNS = "ignore_patterns"
CONF_STORAGE_TYPE = "storage_type"
CONF_UPDATE_INTERVAL = "update_interval"
CONF_ZOMBIE_GRACE_MINUTES = "zombie_grace_minutes"
CONF_BATTERY_GRACE_MINUTES = "battery_grace_minutes"

# Defaults
DEFAULT_NAME = "System: HA - Global Health Score"
DEFAULT_STORAGE_TYPE = "sd-card"
DEFAULT_UPDATE_INTERVAL = 60  # seconds

# Storage type choices for the config flow dropdown
STORAGE_TYPES: list[str] = ["sd-card", "ssd", "emmc"]

# Internal hass.data key holding the boot-time baseline used by zombie
# detection to ignore last_changed values restored from the recorder.
DATA_BOOT_TIME = "_boot_time"

# Grace periods (minutes) before an unavailable / unknown entity becomes a
# zombie.  Both values are user-configurable in the OptionsFlow; the values
# below are the defaults if nothing is set. Battery-class entities get a
# separate, typically longer window because Zigbee / Homematic coordinators
# routinely take longer than 15 minutes to re-poll low-priority devices
# after a restart (#62).
DEFAULT_ZOMBIE_GRACE_MINUTES = 5
DEFAULT_IGNORE_LABEL_NAME = "haghs_ignore"
DEFAULT_BATTERY_GRACE_MINUTES = 60

# Maximum number of entity ids carried in the `zombie_entities` state
# attribute. The Home Assistant state machine caps the entire attribute
# payload at 16 KB; 100 entity ids (with the `[unregistered] ` prefix
# accounted for) stay well below that. `zombie_count` and the per-domain
# breakdown always reflect the full count, only the listing is capped.
ZOMBIE_LIST_CAP = 100

# Internal hass.data key holding the per-entity first-seen timestamps for
# pending updates (#26). Only updates that have been available longer than
# UPDATE_GRACE_DAYS contribute to the update_count penalty; this avoids
# punishing normal user behaviour (most updates land within a few days).
DATA_UPDATE_FIRST_SEEN = "_update_first_seen"
UPDATE_GRACE_DAYS = 7

# ---------------------------------------------------------------------------
# Recommendation templates (i18n-ready — mirrored in strings.json)
#
# Templates use str.format() placeholders so translations can reorder them.
# ---------------------------------------------------------------------------
REC_CPU_LOAD_PSI = "\u26a1 Optimization: PSI CPU stall time is impacting score ({cpu_pct:.1f}%)."
REC_CPU_LOAD_CLASSIC = "\u26a1 Optimization: CPU utilization is impacting score ({cpu_pct:.1f}%)."
REC_RAM_PRESSURE_PSI = (
    "\u26a1 Optimization: PSI memory stall time is impacting score ({ram_pct:.1f}%)."
)
REC_RAM_PRESSURE_CLASSIC = (
    "\u26a1 Optimization: Memory utilization is impacting score ({ram_pct:.1f}%)."
)
REC_IO_PRESSURE = "\u26a1 Optimization: I/O pressure is impacting score ({io_pct:.1f}%)."
REC_DISK_SD_LOW = "\u26a0\ufe0f Disk Space: Only {free_gb:.1f} GB free on {storage_type}!"
REC_DISK_SSD_LOW = "\u26a0\ufe0f Disk Space: Less than 10% free ({free_gb:.1f} GB)!"
REC_DB_OVER_LIMIT = (
    "\U0001f5c4\ufe0f Database: DB ({db_gb:.1f} GB) exceeds dynamic limit ({limit_gb:.1f} GB)."
)
REC_BACKUP_STALE = "\U0001f6a8 Security: Stale backup detected!"
REC_UPDATES_PENDING = "\U0001f4e6 Maintenance: {count} update(s) pending."
REC_ZOMBIES = "\U0001f9df Hygiene: {count} zombie(s) detected."
REC_CORE_LAG = "\U0001f474 Legacy: Core version is >3 months old."
REC_POWER_UNSTABLE = "\u26a0\ufe0f Power: Under-voltage detected — unstable power supply!"
REC_ALL_CLEAR = "\u2705 System optimized"

# Fallback text for empty lists in state attributes
ATTR_NONE = "None"

# Marker prefix for zombie entities that exist in the state machine but
# have no entity registry entry. Surfaces these "ghost" entities in the
# zombie_entities attribute so users can locate them in HA logs.
ATTR_UNREGISTERED_PREFIX = "[unregistered] "

# Boolean recommendation flags exposed as state attributes alongside the
# existing 'recommendations' string. Dashboards and external integrations
# (e.g. HA Pulse) read these via state_attr(sensor, 'rec_*') instead of
# parsing the rendered text. Keep this in sync with _build_rec_flags() in
# coordinator.py.
REC_FLAG_KEYS: tuple[str, ...] = (
    "rec_cpu_load",
    "rec_ram_pressure",
    "rec_io_pressure",
    "rec_disk_low",
    "rec_db_over_limit",
    "rec_power_unstable",
    "rec_backup_stale",
    "rec_updates_pending",
    "rec_zombie",
    "rec_core_lag",
)


@dataclass(frozen=True, slots=True, order=True)
class VersionInformation:
    """Version information."""

    def __repr__(self) -> str:
        return f"{self.major}.{self.minor}"

    major: int
    minor: int


class IssueIds(StrEnum):
    """Issue ids."""

    FALLBACK_MISSING = "fallback_missing"


# Current config entry version. Bumped whenever entry.data/options need
# migration. Keep this in const.py so both config_flow and the migration
# logic in __init__.py reference the same source of truth.
_CONFIG_VERSION = VersionInformation(major=3, minor=4)
