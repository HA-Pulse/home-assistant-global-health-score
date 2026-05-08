"""Constants for the HAGHS integration."""

from dataclasses import dataclass
from enum import StrEnum

DOMAIN = "haghs"

# Config Keys
CONF_CPU_SENSOR = "cpu_sensor"
CONF_RAM_SENSOR = "ram_sensor"
CONF_DB_SENSOR = "db_sensor"
CONF_IGNORE_LABEL = "ignore_label"
CONF_STORAGE_TYPE = "storage_type"
CONF_UPDATE_INTERVAL = "update_interval"

# Defaults
DEFAULT_NAME = "System: HA - Global Health Score"
DEFAULT_STORAGE_TYPE = "sd-card"
DEFAULT_UPDATE_INTERVAL = 60  # seconds

# Storage type choices for the config flow dropdown
STORAGE_TYPES: list[str] = ["sd-card", "ssd", "emmc"]

# ---------------------------------------------------------------------------
# Recommendation templates (i18n-ready — mirrored in strings.json)
#
# Templates use str.format() placeholders so translations can reorder them.
# ---------------------------------------------------------------------------
REC_CPU_LOAD = "\u26a1 Optimization: CPU load is impacting score ({cpu_pct:.1f}%)."
REC_RAM_PRESSURE = "\u26a1 Optimization: Memory pressure is impacting score ({ram_pct:.1f}%)."
REC_IO_PRESSURE = "\u26a1 Optimization: I/O pressure is impacting score ({io_pct:.1f}%)."
REC_DISK_SD_LOW = (
    "\u26a0\ufe0f Disk Space: Only {free_gb:.1f} GB free on {storage_type}!"
)
REC_DISK_SSD_LOW = (
    "\u26a0\ufe0f Disk Space: Less than 10% free ({free_gb:.1f} GB)!"
)
REC_DB_OVER_LIMIT = (
    "\U0001f5c4\ufe0f Database: DB ({db_gb:.1f} GB) exceeds "
    "dynamic limit ({limit_gb:.1f} GB)."
)
REC_BACKUP_STALE = "\U0001f6a8 Security: Stale backup detected!"
REC_UPDATES_PENDING = "\U0001f4e6 Maintenance: {count} update(s) pending."
REC_ZOMBIES = "\U0001f9df Hygiene: {count} zombie(s) detected."
REC_CORE_LAG = "\U0001f474 Legacy: Core version is >3 months old."
REC_POWER_UNSTABLE = "\u26a0\ufe0f Power: Under-voltage detected — unstable power supply!"
REC_ALL_CLEAR = "\u2705 System optimized"

# Fallback text for empty lists in state attributes
ATTR_NONE = "None"


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
