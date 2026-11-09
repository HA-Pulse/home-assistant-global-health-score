[← Back to the README](https://github.com/HA-Pulse/home-assistant-global-health-score/blob/main/README.md)

# Scoring

How the hardware and application pillars are scored: every component, threshold, penalty and cap in full. The README has the short version.

## Pillar 1: Hardware Performance (40%)

Evaluates the physical constraints of the host machine using real system metrics. The hardware score is the average of all available component scores (CPU, RAM, I/O, Disk).

* **Metric Source (Smart Fallback):** HAGHS reads **Pressure Stall Information (PSI)** directly from the Linux kernel (`/proc/pressure/cpu`, `/proc/pressure/memory`, `/proc/pressure/io`). If PSI is unavailable, it automatically falls back to the manually configured CPU/RAM sensors. PSI measures real *stall time* (how long tasks waited for a resource), while classic sensors measure *utilization* (how busy a resource is). Because these scales differ fundamentally, HAGHS uses **separate threshold tiers** for each source.

<details>
<summary><b>Penalty tier tables</b> - exact thresholds for CPU, RAM, and I/O</summary>

* **CPU Load (Tiered):**

  | | Classic Sensor (Utilization) | PSI (Stall Time) |
  |---|---|---|
  | No penalty | 0–25% | 0–5% |
  | Light (10 pts) | 26–40% | 6–15% |
  | Medium (25 pts) | 41–60% | 16–30% |
  | Heavy (50 pts) | 61–80% | 31–50% |
  | Critical (80 pts) | >80% | >50% |

* **Memory Pressure (Tiered):**

  | | Classic Sensor (Utilization) | PSI (Stall Time) |
  |---|---|---|
  | No penalty | 0–69% | 0–5% |
  | Gradual ramp | 70–89% (linear) | — |
  | Light (10 pts) | — | 6–10% |
  | Medium (25 pts) | — | 11–25% |
  | Heavy (50 pts) | — | 26–40% |
  | Critical (80 pts) | ≥90% | >40% |

* **I/O Pressure (PSI-only):** Only available on systems with PSI support. Measures disk/storage stall time.

  | | PSI I/O (Stall Time) |
  |---|---|
  | No penalty | 0–5% |
  | Light (10 pts) | 6–15% |
  | Medium (25 pts) | 16–30% |
  | Heavy (50 pts) | 31–50% |
  | Critical (80 pts) | >50% |

</details>

  > When PSI I/O is available, the hardware score uses **4 components** (CPU + RAM + I/O + Disk) / 4. Without I/O, it falls back to **3 components** (CPU + RAM + Disk) / 3. Without PSI, a CPU or RAM value whose sensor is not selected is **not measured** and left out of the average (never counted as 0 % load); `cpu_ram_source` and `rec_cpu_ram_unmeasured` show it.

**PSI-aware recommendations:** The advisor text is split into PSI and classic variants for CPU and RAM. On PSI-equipped systems you see "PSI CPU stall time is impacting score (12.5%)" (the actual blocking time); on fallback systems "CPU utilization is impacting score (65.0%)" (the busy-ness). The metric source is always explicit so you know whether you are looking at stalls or load.

**Translatable recommendations:** The advisor texts are translatable. English is built in as the fallback; a `translations/<language>.json` file can override any template, and missing keys automatically fall back to English. Translations: English (built in), Brazilian Portuguese, German.

**Power supply detection (Raspberry Pi):** HAGHS auto-detects `binary_sensor.rpi_power_status` when available and applies a flat **20-point** hardware penalty while under-voltage is reported.

* **Storage Integrity (Smart Thresholds):** Disk usage is **auto-detected** via `psutil`, no manual sensor needed. Thresholds adapt to your storage type:
  * **SD-Card / eMMC:** Critical at **<3 GB free**, Warning at **<5 GB free**.
  * **SSD:** Warning at **<10% free** space.

## Pillar 2: Application Hygiene (60%)

Measures "maintenance debt", the hidden factors that cause sluggishness, failed backups, and slow restarts. Every point difference below 100 is explained: each deduction and each unearned bonus prints a recommendation line and sets a matching `rec_*` flag (after a failed update cycle the score keeps its last value, or a neutral one before the first result, and the recommendations show only the failure warning).

* **Zombie Entities (Ratio-based, max 20 pts, hard-cap at 99):** Detects entities with `unavailable` or `unknown` state in 22 physical/UI-relevant domains (automations, scripts, etc. are excluded). Penalties scale with the percentage of zombies relative to the entities in the monitored domains. Two **configurable grace periods** prevent false positives: a regular window (default **5 min**) for all zombie-eligible entities and an extended window (default **60 min**) for `device_class: battery`. Both are adjustable in the Options Flow (1–240 min each). **Disabled** entities are silently ignored - disabling an entity in HA is an alternative to applying an ignore label. While at least one zombie is reported, the application score is **hard-capped at 99** so the Config-Audit bonus can never mask a real zombie. The `zombie_entities` attribute lists up to **100** entries (the recorder's 16 KB attribute limit). Entities without an entity-registry entry (YAML-defined templates, Utility Meter, Riemann Sum, ...) are **not** zombies: when they are `unavailable` or `unknown` past the grace period in the monitored domains, they are reported separately as *unregistered* (`unregistered_count`, `unregistered_entities`, `unregistered_count_per_domain`) and do **not** affect the score. `zombie_count` and `zombie_count_per_domain` always carry the full totals. A zombie is an availability signal, not proof that an entity is orphaned, unused or safe to delete: a temporary outage, an idle device or an entity that only reports in some operating modes looks the same. Before deleting an entity, check its integration, device and config entry. When `zombie_count` is higher than the 100 listed entries, `zombie_count_per_domain` and `zombie_count_per_integration` show where the rest come from.
  
* **Dead Devices (informational, no score impact):** Flags devices only when all monitored entities in `ZOMBIE_DOMAINS` are `unavailable` beyond their respective grace periods. `unknown` does not count as an outage, and entities outside the monitored domains are excluded. Devices without monitored entities are not flagged. Reported via `dead_device_count`, `dead_devices` and the `rec_dead_devices` flag. Entity-level zombie points stay authoritative, so no second penalty is added. A dead device is hidden only when all of its monitored entities are ignored (device label, or every entity by label or pattern).

* **Empty Devices (informational, no score impact):** Flags devices that have no entity at all in the entity registry (disabled entities included), using Home Assistant facts only: the device is not disabled, not a service entry, no other device is connected through it (hubs and bridges are skipped), it has no child devices and is not a merged (composite) device, and its config entry is loaded. Typical leftovers after removing or re-pairing a device. Respects ignore labels on the device and its area; nothing is checked before the zombie grace period has passed after a restart. Reported via `empty_device_count`, `empty_devices` and the `rec_empty_devices` flag (#93).

* **Database Hygiene (Dynamic Limit):** Database size is **auto-detected** for the built-in SQLite database, no manual FileSize sensor or YAML needed. For **external databases** (MariaDB, PostgreSQL), you can configure a custom database size sensor in the setup or options menu (see [External Database](https://github.com/HA-Pulse/home-assistant-global-health-score/blob/main/docs/configuration.md#external-database-mariadb)). The limit scales with your system: `Limit_MB = 1000 + (Total_Entities × 2.5)`. Example: 200 entities = 1.5 GB limit. Above the limit the database costs **10 pts**, above 2.5 times the limit **30 pts**.
  
* **Updates & Core Age:** Tracks pending updates and lists them by name (e.g., `pending_updates: ["ESPHome 2024.2"]`). Pending updates only contribute to the penalty after HAGHS has seen them pending for **7 days**, counted from the first time HAGHS saw that version offered, also across restarts; a newer offered version starts its own 7 days. The list shows them immediately, only the score is delayed. Each grace-aged update costs **5 pts**, Core lag (≥3 months) adds **20 pts**, capped at **35 pts** total. Update entities respect the same ignore labels and patterns as zombie detection; disabled update entities are excluded automatically.
  
* **Integration Health:** Natively detects integrations stuck in `SETUP_ERROR`, `SETUP_RETRY`, or `FAILED_UNLOAD` via HA's ConfigEntry API. Penalty: **5 pts per unhealthy config entry**, capped at **15 pts**. The affected entries are counted in `integration_unhealthy_count` and reported in the recommendations.
  
* **Repairs:** Open repair issues from HA's issue registry cost **5 pts each**, capped at **10 pts**. Counted are only issues that are currently active, not dismissed and owned by another integration; repairs raised by HAGHS itself describe the integration's own prerequisites and are excluded. While any repair is open, the application score is **hard-capped at 99** - the Config-Audit bonus can never mask a broken integration. Count and list are exposed as `repair_count` and `repairs`, the flag is `rec_repairs`. To take a repair out of the score, use HA's native **"Ignore"** action on it (Settings > Repairs); no HAGHS option is needed. Note that a broken backend often raises a repair issue *and* leaves its config entry unhealthy, so one root cause can cost up to **25 pts** together (15 integration health + 10 repairs).
  
* **Backup Health:** A static **30-point deduction** for stale backups.
  
* **Watched entities (Stale reporting, opt-in):** Each overdue watched entity costs 5 application points, capped at 10 before the configuration bonus. While a watched entity is overdue, the application score cannot exceed 99. Only entities with one of the selected stale watch labels set directly on them count, once Home Assistant has not received a report for longer than the stale threshold (default 24 hours); unknown, unavailable and ignored entities are excluded. Details in [Stale reporting](https://github.com/HA-Pulse/home-assistant-global-health-score/blob/main/docs/configuration.md#stale-reporting).
  
* **Config Audit (Bonus):** Awards up to **+10 points** for good recorder hygiene: a recorder retention of at most 10 days, Home Assistant's default (+5), and a user-set include/exclude entity filter (+5). Unearned bonus points are reported in the recommendations and in `rec_config_audit` (meaning "bonus points are missing", not "the configuration is bad").
