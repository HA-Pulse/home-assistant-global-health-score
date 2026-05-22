<img width="460" alt="logo@2xzugeschnitten" src="https://github.com/user-attachments/assets/63f439f2-58ab-4306-9e34-932b74a30d6d" />


**The open standard for Home Assistant instance health monitoring.**

[![HACS Default](https://img.shields.io/badge/HACS-Default-41BDF5.svg?style=for-the-badge)](https://github.com/hacs/integration)
[![GitHub Release](https://img.shields.io/github/v/release/d-n91/home-assistant-global-health-score?style=for-the-badge&color=green)](https://github.com/d-n91/home-assistant-global-health-score/releases)
![Tracked Installs](https://img.shields.io/badge/dynamic/json?color=41BDF5&logo=home-assistant&label=Tracked%20Installs&suffix=%2B&cacheSeconds=15600&style=for-the-badge&url=https://analytics.home-assistant.io/custom_integrations.json&query=$.haghs.total)
[![GitHub Stars](https://img.shields.io/github/stars/d-n91/home-assistant-global-health-score?style=for-the-badge&color=yellow)](https://github.com/D-N91/home-assistant-global-health-score/stargazers)
[![Buy Me a Coffee](https://img.shields.io/badge/Support%20My%20Work-buy%20me%20a%20coffee-yellow?style=for-the-badge&logo=buy-me-a-coffee&logoColor=white)](https://www.buymeacoffee.com/DN91)
![AI-Assisted](https://img.shields.io/badge/AI-Assisted-blue?style=for-the-badge)

---
[![Codacy Badge](https://api.codacy.com/project/badge/Grade/22d138d764884b0380033fb33d7c1875)](https://app.codacy.com/gh/D-N91/home-assistant-global-health-score?utm_source=github.com&utm_medium=referral&utm_content=D-N91/home-assistant-global-health-score&utm_campaign=Badge_Grade)

## Abstract
As Home Assistant matures into a mission-critical Smart Home OS, the need for a unified stability metric becomes paramount. **HAGHS** is a fully local, open-scoring framework designed to provide an objective **Health Score (0-100)**. It differentiates between transient hardware load and chronic maintenance neglect, providing users with a "North Star" for instance optimization. All scoring logic is fully visible in the codebase, no hidden penalties, no black boxes.

---

## Mission

- **Short-term:** Establish HAGHS as the community standard for Home Assistant instance health monitoring.
- **Long-term:** Propose HAGHS as a native HA Core feature, bringing unified health scoring to every Home Assistant installation by default. With user consent, HAGHS metrics should help the Home Assistant project understand how the software is being used and how healthy instances are across the ecosystem.

---
### Featured In
- [How-To Geek](https://www.howtogeek.com/this-tool-gave-my-home-assistant-server-a-rating-and-told-me-how-to-improve-it/) — *"This tool gave my Home Assistant server a rating (and told me how to improve it)"*
- [XDA Developers](https://www.xda-developers.com/tool-graded-home-assistant-server-told-how-make-better/) — *"This tool graded my Home Assistant server and told me how to make it better"*
- [SmartHütte Podcast](https://www.youtube.com/watch?v=G892ii7YTL8&t=48s) — Episode 30, at 0:48 (German)
- [HomeTech.fm Podcast](https://www.youtube.com/watch?v=IrIW2VR7qic&t=3676s) — Episode 569, at 1:01:16 (English)
- [Simon42 Youtube Video](https://www.youtube.com/watch?v=btd66ndsUuA) - Interview with D-N91, creator of HAGHS (German)
- [Tristans Smartes Heim Youtube Video](https://www.youtube.com/watch?v=oDUdchF1mww&t=20s) - Clean up your Home Assistant (German)
---

### Upgrading

HAGHS v2.3 ships a full `async_migrate_entry` handler that converts config entries from version 1, 2 (any minor), 3.0, 3.1, 3.2, and 3.3 to the current 3.4 layout automatically on the next restart. **No manual remove/re-add is needed**, including for users previously affected by the *"Migration handler not found"* warning on v2.2.x (#75).

---

## Table of Contents
- [The HAGHS Standard](#the-haghs-standard)
- [Pillar 1: Hardware Performance (40%)](#pillar-1-hardware-performance-40)
- [Pillar 2: Application Hygiene (60%)](#pillar-2-application-hygiene-60)
- [Configuration](#configuration)
  - [Prerequisites](#1-prerequisites)
  - [Installation & Setup](#2-installation--setup)
  - [Options Flow](#3-options-flow-runtime-settings)
  - [External Database](#external-database)
- [Label Configuration](#label-configuration-smart-whitelisting)
- [Sensor Attributes](#sensor-attributes)
- [Roadmap](#roadmap)
- [UI Integration](#ui-integration)
  - [HAGHS Lite](#haghs-lite-v11-quick-check)
  - [HAGHS Pro](#haghs-pro-v12-command-center)
- [FAQ](#faq)
- [Changelog](#changelog)

---

## The HAGHS Standard

The index is calculated via a weighted average of two core pillars, prioritizing long-term software hygiene over temporary hardware fluctuations.

### The Global Formula

$$Score_{Global} = \lfloor (Score_{Hardware} \cdot 0.4) + (Score_{Application} \cdot 0.6) \rfloor$$

*Note: We use **Floor Rounding** (Integer) to ensure a "Perfect 100" is only achieved by truly optimized systems. Even a minor penalty will drop the score to 99.*

---

## Pillar 1: Hardware Performance (40%)

Evaluates the physical constraints of the host machine using real system metrics. The hardware score is the average of all available component scores (CPU, RAM, I/O, Disk).

* **Metric Source (Smart Fallback):** HAGHS reads **Pressure Stall Information (PSI)** directly from the Linux kernel (`/proc/pressure/cpu`, `/proc/pressure/memory`, `/proc/pressure/io`) for high-precision measurements. If PSI is unavailable (Windows, older Docker, non-Linux hosts), it automatically falls back to the manually configured CPU/RAM sensors. PSI measures real *stall time* (how long tasks waited for a resource), while classic sensors measure *utilization* (how busy a resource is). Because these scales differ fundamentally, HAGHS uses **separate threshold tiers** for each source.

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

* **I/O Pressure (PSI-only):** Only available on systems with PSI support. Measures disk/storage stall time, directly affects recorder writes, automation execution, and restart speed.

  | | PSI I/O (Stall Time) |
  |---|---|
  | No penalty | 0–5% |
  | Light (10 pts) | 6–15% |
  | Medium (25 pts) | 16–30% |
  | Heavy (50 pts) | 31–50% |
  | Critical (80 pts) | >50% |

</details>

  > When PSI I/O is available, the hardware score uses **4 components** (CPU + RAM + I/O + Disk) / 4. Without I/O, it falls back to **3 components** (CPU + RAM + Disk) / 3.

**PSI-aware recommendations:** The advisor text is split into PSI and classic variants for CPU and RAM. On PSI-equipped systems you see "PSI CPU stall time: 12.5%" (the actual blocking time); on fallback systems "CPU utilization: 65%" (the busy-ness). The metric source is always explicit so you know whether you are looking at stalls or load.

**Power supply detection (Raspberry Pi):** HAGHS auto-detects `binary_sensor.rpi_power_status` when available and applies a flat **20-point** hardware penalty while under-voltage is reported. Surfaces silent throttling on undersized power supplies that classic CPU sensors cannot see.

* **Storage Integrity (Smart Thresholds):** Disk usage is **auto-detected** via `psutil`, no manual sensor needed. Thresholds adapt to your storage type:
  * **SD-Card / eMMC:** Critical at **<3 GB free**, Warning at **<5 GB free**.
  * **SSD:** Warning at **<10% free** space.

---

## Pillar 2: Application Hygiene (60%)

Measures "maintenance debt", the hidden factors that cause sluggishness, failed backups, and slow restarts.

* **Zombie Entities (Ratio-based, max 20 pts, hard-cap at 99):** Penalties scale with the percentage of zombies relative to the entities in the monitored domains (22 physical/UI-relevant domains; helpers, automations, scripts etc. are excluded so the ratio is not diluted). Two **configurable grace periods** prevent false positives: a regular window (default **15 min**) for all zombie-eligible entities and an extended window (default **60 min**) for `device_class: battery` because Zigbee / Homematic radios routinely take longer than 15 minutes to re-poll low-priority devices after a coordinator restart. Both are adjustable in the Options Flow (1–240 min each). **Disabled** entities are silently ignored - toggling *Disable entity* in HA is now an alternative to applying an ignore label. While at least one zombie is reported, the application score is **hard-capped at 99** so the Config-Audit bonus can never mask a real zombie. The `zombie_entities` attribute lists up to **100** entries (16 KB state-machine limit); ghost zombies without an entity-registry entry are surfaced with a `[unregistered]` prefix. `zombie_count` and the new `zombie_count_per_domain` attribute always carry the full totals.
  
* **Database Hygiene (Dynamic Limit):** Database size is **auto-detected** for the built-in SQLite database, no manual FileSize sensor or YAML needed. For **external databases** (MariaDB, PostgreSQL), you can configure a custom database size sensor in the setup or options menu (see [External Database](#external-database) below). The limit scales with your system: `Limit_MB = 1000 + (Total_Entities × 2.5)`. Example: 200 entities = 1.5 GB limit.
  
* **Updates & Core Age:** Tracks pending updates and lists them by name (e.g., `pending_updates: ["ESPHome 2024.2"]`). To avoid punishing normal user behaviour (most updates land within a few days), pending updates only contribute to the penalty after a **7-day grace period** - the list shows them immediately, only the score is delayed. Each grace-aged update costs **5 pts**, Core lag (>3 months) adds **20 pts**, capped at **35 pts** total. Update entities respect the same ignore labels and patterns as zombie detection; disabled update entities are excluded automatically.
  
* **Integration Health:** Natively detects integrations stuck in `SETUP_ERROR`, `SETUP_RETRY`, or `FAILED_UNLOAD` via HA's ConfigEntry API, the same states shown as "error" on the Integrations page. Penalty: **5 pts per unhealthy integration**, capped at **15 pts**.
  
* **Backup Health:** A static **30-point deduction** for stale backups.
  
* **Config Audit (Bonus):** Awards up to **+10 points** for good recorder hygiene, purge days configured (+5) and entity filters active (+5).

---

## Configuration

HAGHS is installed via **HACS** and configured via the **UI**

### 1. Prerequisites

Install the built-in **System Monitor** integration via **Settings > Devices & Services > Add Integration** and search for "System Monitor". This is a **native HA integration**, it is not available in HACS.

After adding it, navigate to its entity list and **manually enable** the following two entities (they are disabled by default):
* `sensor.system_monitor_processor_use` (Percentage %)
* `sensor.system_monitor_memory_usage` (Percentage %)

> **Note:** On most Linux-based HA installations (HAOS, Supervised), HAGHS uses PSI data automatically and these sensors are only a safety net. They are still required during setup but may not be actively used for scoring.
> > **If PSI disappears after setup:** Should the kernel stop exposing PSI (e.g. after switching from HAOS to a non-Linux host) and no CPU/RAM fallback sensors are configured, HAGHS surfaces a **Repair flow** in *Settings > System > Repairs* instead of crashing. The flow lets you pick the fallback sensors and resume operation without restarting Home Assistant.

**That's it.** Database size and disk usage are detected automatically. No `configuration.yaml` changes needed.

### 2. Installation & Setup
1.  Download **HAGHS** in **HACS** and **Restart Home Assistant**.
> **Note on HACS installation:** Each release attaches a pre-built `haghs.zip` asset (see the GitHub Releases page). HACS uses this asset automatically; users on legacy versions can also download it manually and drop the contents into `<config>/custom_components/haghs/`
2.  Go to **Settings > Devices & Services > Integrations > Add Integration** and search for **HAGHS**.
3.  Follow the setup mask:
    * Select your **CPU** and **RAM** sensors (smart PSI fallback - only used if PSI data is not available on your host).
    * Choose your **Storage Type** (SD-Card / SSD / eMMC, default: SD-Card).
    * Optionally select one or more **Ignore labels** (multi-select, default: empty).
    * Optionally fill the **Ignore entity-id patterns** field with glob patterns.
    * Optionally select a **Database Size Sensor** for external databases (see the collapsible block below).

### 3. Options Flow (Runtime Settings)
After setup, go to **Settings > Devices & Services > Integrations > HAGHS > Configure** to adjust:
* CPU / RAM sensors
* Storage type
* **Ignore labels** (multi-select)
* **Ignore entity-id patterns** (glob list)
* **Database size sensor** (for external databases)
* **Update interval** (10–3600 seconds, default: 60s)
* **Zombie grace period** (1–240 minutes, default: 15) - how long an entity must stay `unavailable` / `unknown` before it counts as a zombie. Lower values make detection more aggressive; higher values mask short outages.
* **Battery-class grace period** (1–240 minutes, default: 60) - extended window for entities with `device_class: battery`. Zigbee / Homematic radios routinely take longer than the regular window to re-poll battery devices, so a longer default avoids false positives. Independent from the regular grace; can be set lower if you do not care about that distinction.

Changes apply immediately, no restart required.

<details>
<summary><b>External Database (MariaDB / PostgreSQL)</b> - full SQL-sensor walkthrough</summary>

### External Database (MariaDB)

If you use an **external database** (MariaDB) instead of the built-in SQLite, HAGHS cannot auto-detect the database size. To enable database monitoring for your setup:

**1. Create a SQL sensor (no YAML needed):**

Go to **Settings > Devices & Services > Add Integration > search "SQL"** and fill in:

- **Database URL:** `mysql://USER:PASSWORD@IP_ADDRESS/homeassistant?charset=utf8mb4`
  *(Leave empty if MariaDB is already configured as your Recorder database)*
- **Name:** `MariaDB Size`
- **Query:**
  ```sql
  SELECT ROUND(SUM(data_length + index_length) / 1024 / 1024, 2) AS size_mb
  FROM information_schema.tables
  WHERE table_schema = 'homeassistant';
  ```
  *(Replace `homeassistant` with your actual database name)*
- **Column:** `size_mb`

In **Advanced Options:**

- **Unit of Measurement:** `MB`
- **Device Class:** `Data size`
- **State Class:** `Measurement`

### Alternative (PostgreSQL)

If you use PostgreSQL instead of MariaDB, replace the SQL query with:

```sql
SELECT ROUND(pg_database_size('homeassistant') / 1024.0 / 1024.0, 2) AS size_mb;
```

(Replace `homeassistant` with your actual database name.)

Credit: [@cryptomilk](https://github.com/cryptomilk) in [#82](https://github.com/D-N91/home-assistant-global-health-score/issues/82).


**2. Select the sensor in HAGHS:**

Go to **Settings > Devices & Services > Integrations > HAGHS > Configure** and select your new sensor in the **"Database size sensor (optional)"** field.

> **Note:** If left empty, HAGHS uses the built-in SQLite auto-detection. If you use an external database and do not provide a sensor, the database score will simply be neutral (no penalty, no monitoring). The sensor must report the value in **MB**, not bytes, not GB.

</details>

---

## Label Configuration (Smart Whitelisting)
To prevent false positives from sleeping tablets or seasonal devices, you have three ways to exclude entities from HAGHS scoring - pick whichever feels most natural:

1. **Disable the entity** (*Settings > Devices & Services > Entity > Disable entity*). HAGHS now respects `entity_registry.disabled_by` automatically, so disabled entities never count as zombies or contribute to update penalties. No HAGHS configuration needed.
2. **Apply an ignore label** (described below) for entities you want to keep enabled but exclude from scoring (e.g. vacation devices, tablets that sleep).
3. **Use a glob pattern** (see *Pattern-Based Ignore* further down) for entities without a unique ID, which cannot carry a label.

To use ignore labels:
1.  Go to **Settings > Areas, labels & zones > Labels**.
2.  Create one or more labels (e.g. `haghs_ignore`, `vacation`, `guest_mode`).
3.  Open **Settings > Devices & Services > HAGHS > Configure** and add every label you want HAGHS to honour to the **Ignore labels** field. The field accepts a list, so all listed labels are evaluated.
4.  Assign any of those labels to any **Device**, **Entity**, or **Update Entity**.
    * **Pro Tip:** Assigning a label to a **Device** automatically whitelists **all underlying entities** belonging to that specific device.
    * **Update Tip:** Labelled update entities are excluded from the update count and penalty.
    * **Note on `hidden_by`:** Hiding an entity from auto-generated dashboards does **not** exclude it from HAGHS. To exclude a hidden entity, disable it or apply an ignore label.

### Dynamic exclusions via automation

Toggling whether HAGHS ignores a group of entities is done with Home Assistant's
native label services - HAGHS does not need its own service. List a label like
`vacation` in the HAGHS *Ignore labels* field, then assign/remove it from
automations:

```yaml
# Toggle the `vacation` label on a group of entities
# (use label.remove with the same target when vacation ends)
- alias: HAGHS vacation start
  trigger:
    - platform: time
      at: "08:00:00"
  action:
    - service: label.assign
      data:
        label_id: vacation
        target:
          entity_id:
            - light.terrace
            - switch.coffee_machine
            - vacuum.robot
```

HAGHS picks up the change automatically on its next refresh; no reload needed.

### Pattern-Based Ignore (for entities without a unique ID)

Some integrations (e.g. `monitor_docker`, the legacy `torque` sensor) create entities without a unique ID. These exist only in the state machine, have no entity-registry entry, and therefore cannot carry a label. HAGHS would otherwise flag them as zombies as soon as they go unavailable.

Open **Settings > Devices & Services > HAGHS > Configure** and fill the **Ignore entity-id patterns** field with one glob pattern per line. Matching entities are excluded from both zombie detection and update penalties.

Examples:
- `sensor.docker_*` - every Docker monitor sensor
- `sensor.torque_*` - every Torque OBD sensor
- `binary_sensor.test_?` - `binary_sensor.test_1` through `binary_sensor.test_9`

Wildcards `*` and `?` are supported (standard glob syntax). Invalid patterns are logged as a `WARNING` and skipped, so a single typo never disables the rest of the list.

---

## Sensor Attributes

HAGHS exposes the following attributes for use in dashboard cards, automations, and templates:

| Attribute | Type | Description |
|---|---|---|
| `hardware_score` | int | Hardware pillar score (0–100), averaged from CPU, RAM, I/O (if PSI), and Disk |
| `application_score` | int | Application pillar score (0–100) |
| `zombie_count` | int | Total number of zombie entities |
| `zombie_entities`| list | Entity IDs of zombies (capped at 100; ghost zombies prefixed with [unregistered] |
| `zombie_count_per_domain` | dict | Per-domain zombie breakdown (e.g. {"sensor": 3, "switch": 1}); always reflects the full count regardless of the list cap |
| `db_size_mb` | float | Current database size in MB (auto-detected for SQLite, or from external DB sensor if configured) |
| `psi_available` | bool | `True` when PSI provides both CPU and memory data (the prerequisite for `psi.available`). I/O PSI is read independently and may still be present when this is `False`. Disk is always read via `psutil`, never PSI. |
| `recorder_keep_days` | int/null | Configured purge days (null = not set) |
| `recorder_filter_active` | bool | Whether entity filters are active |
| `pending_updates` | list | Names of pending updates (e.g., `["ESPHome 2024.2"]`). Listed immediately; only counted toward the score after a 7-day grace period |
| `recommendations` | string | Advisor recommendations (CPU, RAM, I/O, disk, DB, updates, zombies, backup, core lag) |
| `rec_cpu_load` | bool | CPU load (PSI stall or classic utilization) is currently penalised |
| `rec_ram_pressure` | bool | Memory pressure / utilization is currently penalised |
| `rec_io_pressure` | bool | I/O PSI stall time is currently penalised |
| `rec_disk_low` | bool | Disk free space is below the storage-type threshold |
| `rec_db_over_limit` | bool | Database size exceeds the dynamic limit |
| `rec_power_unstable` | bool | RPi under-voltage detected |
| `rec_backup_stale` | bool | `binary_sensor.backups_stale` is on |
| `rec_updates_pending` | bool | At least one non-ignored update entity is pending |
| `rec_zombie` | bool | At least one zombie entity is reported |
| `rec_core_lag` | bool | HA Core is ≥ 3 minor versions behind latest |

---

## Roadmap

Planned features, declined items, and completed milestones live in [`ROADMAP.md`](./ROADMAP.md). The roadmap follows the HAGHS philosophy: local-only, system-health focus, HA Core compatibility.

---

## UI Integration

HAGHS provides all data as sensor attributes. Dashboard visualization happens entirely in Lovelace, keeping a clean separation between backend (sensor) and frontend (UI).

Below are two ready-to-use card configurations:

### HAGHS Lite v1.1 (Quick Check)

A compact card for a fast overview, score, sub-scores, and actionable links.

![HAGHS Lite v2 2](https://github.com/user-attachments/assets/00ed0c47-bcc7-4ef7-bad4-f76950347e88)

```yaml
type: vertical-stack
cards:
  - type: gauge
    entity: sensor.system_ha_global_health_score
    name: HAGHS
    unit: " "
    needle: true
    severity:
      green: 90
      yellow: 75
      red: 0
  - type: markdown
    content: >
      {% set e = 'sensor.system_ha_global_health_score' %} {% set hw =
      state_attr(e, 'hardware_score') | int(0) %} {% set app = state_attr(e,
      'application_score') | int(0) %} {% set rec = state_attr(e,
      'recommendations') | default('', true) %} {% set updates = state_attr(e,
      'pending_updates') | default([], true) | list %} {% set zombies =
      state_attr(e, 'zombie_count') | int(0) %} {% set psi = state_attr(e,
      'psi_available') | default(false, true) %} {% set _upd =
      '/config/updates' %} {% set _ent = '/config/entities' %}

      Hardware **{{ hw }}**/100 | Application **{{ app }}**/100

      {% if updates | length > 0 %} 📦 {{ updates | length }} update(s) pending
      — [Open Updates]({{ _upd }}) {% endif %}

      {% if zombies > 0 %} 🧟 {{ zombies }} zombie(s) — [Check
      Entities]({{ _ent }}) {% endif %}

      {% if rec not in [none, 'unknown', 'unavailable'] and '✅' not in rec %}
      {{ rec }}
      {% else %} --- ✅ System healthy. No recommendations. {% endif %}

      {% set keep = state_attr(e, 'recorder_keep_days') %}
      {% set filter = state_attr(e, 'recorder_filter_active') | default(false, true) %}
      {% if keep in [none, 'unknown'] or not filter %}
      💡 Tips to improve your score:
      {% if keep in [none, 'unknown'] %} &nbsp;&nbsp; • Set `purge_keep_days` in your recorder configuration (+5 pts){% endif %}
      {% if not filter %} &nbsp;&nbsp; • Configure an `include` / `exclude` entity filter for the recorder (+5 pts){% endif %}
      {% endif %}

      **Metric source**: {% if psi %}🟢 PSI active (CPU + RAM + I/O + Disk) —
      hardware score uses 4 components{% else %}⚙️ Classic sensors (CPU + RAM +
      Disk) — hardware score uses 3 components{% endif %}

```

### HAGHS Pro v1.2 (Command Center)

A comprehensive dashboard with full score breakdown, grouped zombies, database monitoring, recorder health, and deep-links.

![HAGHS Pro](https://github.com/user-attachments/assets/b5b1e3ab-d648-4784-9eb0-5df2513aea57)


```yaml
type: vertical-stack
cards:
  - type: gauge
    entity: sensor.system_ha_global_health_score
    name: HAGHS
    unit: " "
    needle: true
    severity:
      green: 90
      yellow: 75
      red: 0
  - type: markdown
    title: Score Breakdown
    content: >
      {% set e = 'sensor.system_ha_global_health_score' %} {% set hw =
      state_attr(e, 'hardware_score') | int(0) %} {% set app = state_attr(e,
      'application_score') | int(0) %} {% set score = states(e) | int(0) %}

      Hardware **{{ hw }}**/100 | Application **{{ app }}**/100

      Formula: ({{ hw }} × 0.4) + ({{ app }} × 0.6) = {{ score }}
  - type: markdown
    title: 🛡️ Advisor
    content: >
      {% set e = 'sensor.system_ha_global_health_score' %} {% set rec =
      state_attr(e, 'recommendations') | default('', true) %}

      {% if states(e) in ['unavailable', 'unknown'] %}
        ⚠️ Health Advisor sensor is offline.
      {% elif rec not in [none, 'unknown', 'unavailable'] and '✅' not in rec %}
        {{ rec }}
      {% else %}
        ✅ System healthy. No recommendations.
      {% endif %}
  - type: conditional
    conditions:
      - condition: numeric_state
        entity: sensor.system_ha_global_health_score
        attribute: zombie_count
        above: -1
    card:
      type: markdown
      title: 📦 Updates & Maintenance
      content: >
        {% set e = 'sensor.system_ha_global_health_score' %} {% set updates =
        state_attr(e, 'pending_updates') | default([], true) | list %} {% set
        db_mb = state_attr(e, 'db_size_mb') | float(0) %} {% set keep =
        state_attr(e, 'recorder_keep_days') %} {% set filter = state_attr(e,
        'recorder_filter_active') | default(false, true) %} {% set psi =
        state_attr(e, 'psi_available') | default(false, true) %} {% set _upd =
        '/config/updates' %}

        {% if updates | length > 0 %}{{ updates | length }} update(s) pending:<br>
        {% for u in updates %}&nbsp;&nbsp; • {{ u }}<br>{% endfor %}
        [→ Open Updates]({{ _upd }})
        {% else %} ✅ All updates installed {% endif %}

        <hr>

        Database: {{ db_mb | round(1) }} MB {% if db_mb == 0.0 %}*(external DB
        detected)*{% endif %}


        Recorder: {% if keep not in [none, 'unknown'] %}purge active ({{ keep }}
        days){% else %}no purge configured — DB may grow indefinitely{% endif %}


        {{ 'Entity filter active' if filter else 'No entity filter' }}


        {% if keep in [none, 'unknown'] or not filter %}
        💡 Tips to improve your score:
        {% if keep in [none, 'unknown'] %} &nbsp;&nbsp; • Set `purge_keep_days` in your recorder configuration (+5 pts){% endif %}
        {% if not filter %} &nbsp;&nbsp; • Configure an `include` / `exclude` entity filter for the recorder (+5 pts){% endif %}
        {% endif %}


        ---

        **Metric source**: {% if psi %}🟢 PSI active (CPU + RAM + I/O + Disk) —
        hardware score uses 4 components{% else %}⚙️ Classic sensors (CPU + RAM
        + Disk) — hardware score uses 3 components{% endif %}
  - type: markdown
    title: 🧟 Zombie Entities
    content: >
      {% set e = 'sensor.system_ha_global_health_score' %} {% set z_raw =
      state_attr(e, 'zombie_entities') | default([], true) %} {% set z_count =
      state_attr(e, 'zombie_count') | int(0) %}

      {% if z_count == 0 %}
        ✅ No zombie entities detected.
      {% else %}
        {% if z_raw is string %}
          {% set z_list = z_raw.split(',') | map('trim') | list %}
        {% else %}
          {% set z_list = z_raw | list %}
        {% endif %}
        {% set ghosts = z_list | select('match', '^\\[unregistered\\]') | list %}
        {% set tracked = z_list | reject('match', '^\\[unregistered\\]') | list %}
        {% set grouped = expand(tracked) | groupby('domain') %}

        {# Domain count: prefer the HAGHS v2.3+ attribute when present.
           Fall back to extracting the distinct domains from z_list so the
           card keeps working on older HAGHS versions that do not expose
           zombie_count_per_domain. #}
        {% set per_domain = state_attr(e, 'zombie_count_per_domain') %}
        {% if per_domain %}
          {% set domain_count = per_domain | length %}
        {% else %}
          {% set ns = namespace(seen=[]) %}
          {% for entry in z_list %}
            {% set dom = (entry | replace('[unregistered] ', '')).split('.')[0] %}
            {% if dom not in ns.seen %}
              {% set ns.seen = ns.seen + [dom] %}
            {% endif %}
          {% endfor %}
          {% set domain_count = ns.seen | length %}
        {% endif %}

        {{ z_count }} zombie(s) across {{ domain_count }} domain(s)
        {% if per_domain %} ({% for dom, cnt in per_domain.items() %}{{ dom }}: {{ cnt }}{% if not loop.last %}, {% endif %}{% endfor %}){% endif %}
        {% if z_count > z_list | length %}*(showing first {{ z_list | length }} — {{ z_count - z_list | length }} more hidden)*{% endif %}

        {% set _ent = '/config/entities' %}[→ Check Entities]({{ _ent }})

        {% for domain in grouped %}
        <details>
        <summary>{{ domain[0] | title }}: {{ domain[1] | count }}</summary>
        {% for item in domain[1] %}
        &nbsp;&nbsp; • {{ device_attr(item.entity_id, 'name') | default('unknown device', true) }} — {{ item.name }} (`{{ item.entity_id }}`): {{ item.state }}
        {% endfor %}
        </details>
        {% endfor %}

        {% if ghosts | length > 0 %}
        <details>
        <summary>⚠️ Unregistered: {{ ghosts | length }}</summary>
        {% for entry in ghosts %}
        &nbsp;&nbsp; • `{{ entry | replace('[unregistered] ', '') }}`
        {% endfor %}
        </details>
        {% endif %}
      {% endif %}

```

### Lite vs. Pro Comparison

| Feature | Lite | Pro |
|---|:---:|:---:|
| Gauge with score | Yes | Yes |
| Hardware / Application score | Table | Table + live formula |
| Advisor recommendations (CPU, RAM, I/O, ...) | Inline | Dedicated card |
| Pending updates (by name) | Count + link | Full list + deep-link |
| Zombie details (by domain) | Count + link | Grouped + expandable |
| Database size + warning | — | Yes |
| Recorder health (purge + filter) | — | Yes |
| Metric source (PSI vs. Classic + component count) | Yes (detailed) | Yes (detailed) |
| Deep-links to HA settings | Yes | Yes |

---

## FAQ

**Why is my score so low?**
Check the Advisor recommendations in the dashboard card. They tell you exactly where penalties come from (e.g., "5 update(s) pending", "Stale backup detected").

**Does HAGHS send any data to external servers?**
No. All data collection is strictly local. HAGHS reads directly from Linux kernel interfaces (`/proc/pressure/*`), `psutil`, and the HA internal state machine. No outbound network traffic is ever initiated by this integration.

**Does HAGHS work with Docker / Kubernetes?**
Yes. HAGHS auto-detects disk usage and database size on any platform. The Core update entity is detected dynamically, no Supervisor dependency.

**How does PSI work and why does HAGHS use it?**
PSI (Pressure Stall Information) is a Linux kernel feature that measures real resource contention — how long tasks are actually waiting for CPU, memory, or I/O — rather than how busy a resource is. A system at 40% CPU utilization can have near-zero stall time, while one at 20% utilization may be heavily stalled. HAGHS uses PSI as the primary metric where available, falling back to classic utilization sensors on systems without PSI support (Windows, older Docker setups). Because their scales differ fundamentally, HAGHS uses separate penalty thresholds for each. When PSI is active, I/O monitoring is also included, giving a 4-component hardware score (CPU + RAM + I/O + Disk). Without PSI, the score uses 3 components (CPU + RAM + Disk). The classic sensors selected during setup are only used when PSI is unavailable.

**I use an external database (MariaDB / PostgreSQL). How do I monitor it?**
See the [External Database](#external-database) section above for full setup instructions. The sensor must report the database size in **MB**. If no sensor is configured, HAGHS skips database monitoring, no penalty, no scoring, other scores unaffected.

**Do I still need a disk usage sensor?**
No. HAGHS reads disk usage directly via `psutil`. No manual sensor selection required.

**How are update penalties calculated?**
Each pending update costs **5 pts**. A Core version lag (≥3 months behind) adds **20 pts**. The combined penalty is capped at **35 pts**.

**How does the zombie grace period work?**
Entities that just became `unavailable` or `unknown` are ignored for **15 minutes by default**, configurable in the Options Flow from 1 to 240 minutes. This prevents your score from dropping during brief network hiccups or device reboots. Battery-class entities (`device_class: battery`) get a separate, longer window (default 60 minutes) because Zigbee / Homematic coordinators routinely take longer than 15 minutes to re-poll low-priority devices.

**Why is my score capped at 99 right after a restart?**
Two reasons it can happen:
1. **Boot-time grace baseline.** HAGHS uses `max(last_changed, boot_time)` as the floor for the grace window, so entities whose `last_changed` value was restored from the recorder do not bypass the grace period after a restart. A zombie that was already a zombie before the restart still gets the configured grace window from the new boot.
2. **Startup defer.** Zombie detection waits for `EVENT_HOMEASSISTANT_STARTED` before running for the first time. The entity registry (and therefore your ignore labels) only finishes loading at that point; running earlier would produce false positives for labelled-but-unavailable entities.
The hard-cap at 99 while at least one zombie is reported is intentional — the Config-Audit bonus can never lift a "real" zombie issue to 100.

**Why did my score change after upgrading to v2.3?**
v2.3 expanded zombie detection from 9 to 22 domains, added a 7-day grace period before pending updates count, and now hard-caps the application score at 99 while a zombie exists. Most users will see a small **increase** (fewer noisy update penalties, disabled-entity entities no longer counted), but instances with previously unnoticed zombies in the new domains may see a small drop. The Changelog and the in-card *Tips* block explain exactly which factors are active.

**A pending update from yesterday is in the list but doesn't change my score yet — why?**
Because of the 7-day update grace period. The list is informational and shows everything HA reports as pending; the **score** only deducts after a pending update has been available for at least 7 days. This avoids punishing normal user behaviour — most updates land within a few days.

**Can I change the update interval?**
Yes. Go to **Settings > Devices & Services > Integrations > HAGHS > Configure** and adjust the update interval (10–3600 seconds). Lower values give faster updates, higher values save resources.

**What happens if a sub-calculation fails?**
HAGHS uses a safety net: if any pillar calculation times out or throws an error, it falls back to a neutral score (100 / no penalty) and logs a warning. The sensor never crashes.

---

## Changelog

### [v2.3.0] - 2026-05-21

**Highlights**

* **Multi-label ignore + dynamic toggling.** `ignore_labels` now accepts a list; toggle inclusion/exclusion at runtime via HA-native `label.assign` / `label.remove` services (no custom HAGHS service). Migration from the legacy single-label config is automatic.
* **Disabled-entity auto-ignore.** Entities marked *Disable entity* in the entity registry are now excluded from zombie detection and update penalties — no `haghs_ignore` label required.
* **Pattern-based ignore (#64).** New `ignore_patterns` field accepts glob patterns for entities without a unique ID (e.g. `sensor.docker_*`, `sensor.torque_*`).
* **Configurable zombie + battery grace periods.** Two new Options Flow fields (1–240 min each, defaults 15 / 60). Battery-class entities get the longer window because Zigbee / Homematic radios routinely take longer than 15 minutes to re-poll low-priority devices.
* **7-day update grace.** Pending updates only contribute to the penalty after 7 days; the list stays informational so you still see what is queued.
* **ZOMBIE_DOMAINS expanded 9 → 22.** New domains include `alarm_control_panel`, `camera`, `climate`, `cover`, `device_tracker`, `fan`, `humidifier`, `lawn_mower`, `lock`, `media_player`, `number`, `remote`, `select`, `siren`, `text`, `vacuum`, `valve`, `water_heater`. New `zombie_count_per_domain` attribute exposes a per-domain breakdown; `zombie_entities` list cap raised from 20 → 100.
* **Hard-cap at 99 with zombies (#61).** While `zombie_count > 0`, the application score cannot exceed 99 so the Config-Audit bonus can never mask a real issue.
* **Unregistered ghost zombies marked (#61).** Entities without an entity-registry entry are surfaced in `zombie_entities` with a `[unregistered]` prefix and warned in the log.
* **Power Supply Status detection (#21).** Auto-detects `binary_sensor.rpi_power_status` for Raspberry Pi under-voltage and applies a flat 20-point hardware penalty.
* **Boolean `rec_*` recommendation flags.** Ten new state attributes (e.g. `rec_cpu_load`, `rec_zombie`, `rec_backup_stale`) alongside the existing `recommendations` string — easier to consume in templates and automations.
* **PSI-aware recommendation text.** CPU and RAM advice are split into PSI ("12.5% PSI stall time") and classic ("65% CPU utilization") variants so the metric source is always explicit.
* **Config Flow refactor + RepairsFlow (#49).** CPU/RAM fallback sensors are optional when PSI is available. A new Repair flow lets you recover after PSI disappears post-setup without restarting Home Assistant.

**Bug fixes**

* `async_migrate_entry` now shipped — closes the v2.2.x "Migration handler not found" failure for v1/v2 config entries (#75).
* Options Flow no longer reverts cleared optional fields (`db_sensor`, CPU/RAM fallback, ignore labels/patterns) after an HA restart.
* Registry-race guard now correctly defers zombie detection during HA's `starting` phase, not only when HA is fully shut down (previously the guard used `hass.is_running` which is `True` for both `starting` and `running`).
* Battery-class entities get a separate, longer grace window (#62).
* Zombie denominator counts only the 22 zombie-eligible domains, so instances with many automations/scripts/helpers are no longer artificially diluted (#9).
* Restart grace via boot-time baseline so `last_changed` values restored from the recorder no longer bypass the grace window (#10, #27).

**Infrastructure**

* Full test suite bootstrap (`pyproject.toml`, `requirements_test.txt`, seven test modules: zombies, updates, application, hardware-power, migration, recommendations, options-flow).
* CI workflow runs pytest + ruff on every PR.
* Release-notes augmentation workflow auto-injects a coffee-support block and a contributors list into each release body.

**Documentation**

* External database walkthrough (no-YAML SQL-sensor setup, MariaDB query).
* Pattern-Based Ignore documentation.
* Full long-form story in `v2.3_CHANGELOG.md`.

**Minimum Home Assistant version raised** to 2024.10.0 (for `vol.Exclusive`, `IssueSeverity`, and the modern `LabelSelector`).

### [v2.2.2] - 2026-03-30
* **Feature:** Added optional **Database Size Sensor** override for external databases (MariaDB, PostgreSQL). Configurable in both Setup and Options flow. When set, HAGHS uses the sensor value (in MB) instead of SQLite auto-detection. When left empty, the default SQLite behavior is unchanged. No migration needed, existing installations are unaffected.

### [v2.2.1] - 2026-03-29
* **Bugfix:** Fixed absurd percentage values in hardware recommendations (e.g. "Memory pressure is impacting score (5698.1%)") when a manually configured CPU/RAM sensor reports absolute values (MB/MHz) instead of percent. Values above 100% are now clamped and a warning is logged to help users select the correct sensor.

<details>
<summary><b>Older releases (v2.2.0 and earlier)</b></summary>

### [v2.2.0] - 2026-03-29
* **Architecture:** Full async migration to `DataUpdateCoordinator` with safety-net timeouts.
* **Zero-YAML:** Database size and disk usage are now auto-detected. No manual sensors or `configuration.yaml` changes needed.
* **PSI Integration:** Uses Linux Pressure Stall Information for CPU, Memory, and I/O with automatic fallback to classic sensors. Separate penalty tiers for PSI (stall time) vs. classic sensors (utilization), because their scales differ fundamentally.
* **I/O Scoring:** PSI I/O pressure is now actively scored. When available, the hardware pillar uses 4 components (CPU + RAM + I/O + Disk) instead of 3.
* **CPU Threshold Adjustment:** Classic CPU penalty now starts at >25% (was >10%) to avoid penalizing normal system activity.
* **Smart Disk Thresholds:** Storage-type-aware penalties (SD-Card/eMMC: absolute GB; SSD: percentage-based).
* **Dynamic Database Limit:** DB threshold scales with entity count (`1000 + entities × 2.5` MB).
* **Zombie Improvements:** Ratio-based penalties, 15-minute grace period, attribute list capped at 20.
* **Update Improvements:** Ignore label works on updates, core lag threshold raised to 3 months, pending updates listed by name.
* **Config Audit:** Bonus points for good recorder configuration (purge days + entity filters).
* **Integration Health:** Native detection of unhealthy integrations via ConfigEntry state API (SETUP_ERROR, SETUP_RETRY, FAILED_UNLOAD). 5 pts per integration, max 15 pts.
* **Options Flow:** All settings adjustable at runtime without reinstalling.
* **Configurable Interval:** Update frequency adjustable from 10s to 3600s.
* **i18n Ready:** All strings externalized to `strings.json`.
* **Removed:** Log file monitoring (deprecated since v2.0.2).

### [v2.1.1] - 2026-01-29
* **UI Migration:** Transitioned from YAML variables to a full **Config Flow (Setup Mask)**.
* **Optimization:** `haghs_ignore` label on a Device now automatically covers all its entities.

### [v2.0.2] - 2026-01-26
* **Refinement:** Made Log File monitoring explicitly optional to support HAOS users without CLI access.

### [v2.0.0] - 2026-01-26
* **Major:** Added **Database & Log Hygiene** monitoring.
* **Feature:** Implemented **Deep Label Support**.
* **Logic:** Added **Core Age** penalty (>2 months lag).
* **Logic:** Added **Cumulative Update** counting (capped at 35 pts).

### [v1.3.0] - 2026-01-24
* **NEW:** Implemented Single-Point Configuration using Template Variables.
* **NEW:** Added Heavyweight CPU Tiers.
* **Fixed:** Switched to **Floor Rounding** (Integer) for a more honest health assessment.

</details>

---

**AI Disclosure:** While the architectural concept and logic are my own, I utilized AI to assist with code optimization and documentation formatting.
