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
---

### Important: Upgrading from v2.1.x to v2.2+ (Migration Error)
If you are upgrading from an older version and encounter a `Migration handler not found` error in your logs or UI, this is expected behavior.

Version 2.2 introduced a complete architectural rewrite, moving away from manual YAML configurations to a pure auto-detection setup. Because the old stored settings are fundamentally incompatible with the new system, an automatic background migration is not possible.

**How to fix:** Simply delete the existing HAGHS integration from your *Settings > Devices & Services* dashboard, restart Home Assistant, and add the integration fresh.

---

## Table of Contents
- [The HAGHS Standard](#the-haghs-standard-v222)
- [Pillar 1: Hardware Performance (40%)](#pillar-1-hardware-performance-40)
- [Pillar 2: Application Hygiene (60%)](#pillar-2-application-hygiene-60)
- [Configuration](#configuration)
  - [Prerequisites](#1-prerequisites)
  - [Installation & Setup](#2-installation--setup)
  - [Options Flow](#3-options-flow-runtime-settings)
  - [External Database](#external-database)
- [Label Configuration](#label-configuration-smart-whitelisting)
- [Sensor Attributes](#sensor-attributes)
- [UI Integration](#ui-integration)
  - [HAGHS Lite](#haghs-lite-v11-quick-check)
  - [HAGHS Pro](haghs-pro-v11-command-center)
- [FAQ](#faq)
- [Changelog](#changelog)

---

## The HAGHS Standard (v2.2.2)

The index is calculated via a weighted average of two core pillars, prioritizing long-term software hygiene over temporary hardware fluctuations.

### The Global Formula

$$Score_{Global} = \lfloor (Score_{Hardware} \cdot 0.4) + (Score_{Application} \cdot 0.6) \rfloor$$

*Note: We use **Floor Rounding** (Integer) to ensure a "Perfect 100" is only achieved by truly optimized systems. Even a minor penalty will drop the score to 99.*

---

## Pillar 1: Hardware Performance (40%)

Evaluates the physical constraints of the host machine using real system metrics. The hardware score is the average of all available component scores (CPU, RAM, I/O, Disk).

* **Metric Source (Smart Fallback):** HAGHS reads **Pressure Stall Information (PSI)** directly from the Linux kernel (`/proc/pressure/cpu`, `/proc/pressure/memory`, `/proc/pressure/io`) for high-precision measurements. If PSI is unavailable (Windows, older Docker, non-Linux hosts), it automatically falls back to the manually configured CPU/RAM sensors. PSI measures real *stall time* (how long tasks waited for a resource), while classic sensors measure *utilization* (how busy a resource is). Because these scales differ fundamentally, HAGHS uses **separate threshold tiers** for each source.

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

  > When PSI I/O is available, the hardware score uses **4 components** (CPU + RAM + I/O + Disk) / 4. Without I/O, it falls back to **3 components** (CPU + RAM + Disk) / 3.

* **Storage Integrity (Smart Thresholds):** Disk usage is **auto-detected** via `psutil`, no manual sensor needed. Thresholds adapt to your storage type:
  * **SD-Card / eMMC:** Critical at **<3 GB free**, Warning at **<5 GB free**.
  * **SSD:** Warning at **<10% free** space.

---

## Pillar 2: Application Hygiene (60%)

Measures "maintenance debt", the hidden factors that cause sluggishness, failed backups, and slow restarts.

* **Zombie Entities (Ratio-based, max 20 pts):** Penalties scale with the percentage of zombies relative to total entities, not a fixed count. A **15-minute grace period** prevents false positives from temporary network outages. The attribute list is capped at 20 entries to protect the state machine; the full count is always accurate.
* **Database Hygiene (Dynamic Limit):** Database size is **auto-detected** for the built-in SQLite database, no manual FileSize sensor or YAML needed. For **external databases** (MariaDB, PostgreSQL), you can configure a custom database size sensor in the setup or options menu (see [External Database](#external-database) below). The limit scales with your system: `Limit_MB = 1000 + (Total_Entities × 2.5)`. Example: 200 entities = 1.5 GB limit.
* **Updates & Core Age:** Tracks pending updates and lists them by name (e.g., `pending_updates: ["ESPHome 2024.2"]`). Penalizes a "Core Version Lag" of **>3 months** behind the latest release. Each update costs **5 pts**, Core lag adds **20 pts**, capped at **35 pts** total. The `haghs_ignore` label also works on update entities.
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

**That's it.** Database size and disk usage are detected automatically. No `configuration.yaml` changes needed.

### 2. Installation & Setup
1.  Download **HAGHS** in **HACS** and **Restart Home Assistant**.
2.  Go to **Settings > Devices & Services > Integrations > Add Integration** and search for **HAGHS**.
3.  Follow the setup mask:
    * Select your **CPU** and **RAM** sensors (PSI fallback).
    * Choose your **Storage Type** (SD-Card / SSD / eMMC, default: SD-Card).
    * Optionally change the **Ignore Label** (default: `haghs_ignore`).
    * Optionally select a **Database Size Sensor** for external databases (see below).

### 3. Options Flow (Runtime Settings)
After setup, go to **Settings > Devices & Services > Integrations > HAGHS > Configure** to adjust:
* CPU / RAM sensors
* Storage type
* Ignore label
* **Database size sensor** (for external databases)
* **Update interval** (10–3600 seconds, default: 60s)

Changes apply immediately, no restart required.

### External Database

If you use an **external database** (MariaDB, PostgreSQL) instead of the built-in SQLite, HAGHS cannot auto-detect the database size. To enable database monitoring for your setup:

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

**2. Select the sensor in HAGHS:**

Go to **Settings > Integrations > HAGHS > Configure** and select your new sensor in the **"Database size sensor (optional)"** field.

> **Note:** If left empty, HAGHS uses the built-in SQLite auto-detection. If you use an external database and do not provide a sensor, the database score will simply be neutral (no penalty, no monitoring). The sensor must report the value in **MB**, not bytes, not GB.

---

## Label Configuration (Smart Whitelisting)
To prevent false positives from sleeping tablets or seasonal devices:
1.  Go to **Settings > Areas, labels & zones > Labels**.
2.  Create a label named `haghs_ignore`.
3.  Assign this label to any **Device**, **Entity**, or **Update Entity**.
    * **Pro Tip:** Assigning the label to a **Device** automatically whitelists **all underlying entities** belonging to that specific device.
    * **Update Tip:** Labelled update entities are excluded from the update count and penalty.

---

## Sensor Attributes

HAGHS exposes the following attributes for use in dashboard cards, automations, and templates:

| Attribute | Type | Description |
|---|---|---|
| `hardware_score` | int | Hardware pillar score (0–100), averaged from CPU, RAM, I/O (if PSI), and Disk |
| `application_score` | int | Application pillar score (0–100) |
| `zombie_count` | int | Total number of zombie entities |
| `zombie_entities` | list | Entity IDs of zombies (capped at 20) |
| `db_size_mb` | float | Current database size in MB (auto-detected for SQLite, or from external DB sensor if configured) |
| `psi_available` | bool | Whether PSI metrics are active (CPU + RAM + I/O). When `false`, only classic sensors are used (CPU + RAM, no I/O) |
| `recorder_keep_days` | int/null | Configured purge days (null = not set) |
| `recorder_filter_active` | bool | Whether entity filters are active |
| `pending_updates` | list | Names of pending updates (e.g., `["ESPHome 2024.2"]`) |
| `recommendations` | string | Advisor recommendations (CPU, RAM, I/O, disk, DB, updates, zombies, backup, core lag) |

---

## Roadmap

The roadmap is a living document. New ideas are collected, evaluated, and added here once they are deemed viable and aligned with the HAGHS philosophy:

- **Local-only:** Features must never introduce outbound network traffic or cloud dependencies.
- **System health focus:** Purely decorative features are rejected. Every addition must serve instance health monitoring.
- **HA Core compatibility:** All new code must follow HA Core standards to support the long-term goal of native adoption.

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

      | Hardware | Application | | **{{ hw }}**/100 | **{{ app }}**/100 |

      {% if updates | length > 0 %} 📦 {{ updates | length }} update(s) pending
      — [Open Updates]({{ _upd }}) {% endif %}

      {% if zombies > 0 %} 🧟 {{ zombies }} zombie(s) — [Check
      Entities]({{ _ent }}) {% endif %}

      {% if rec not in [none, 'unknown', 'unavailable'] and '✅' not in rec %} {%
      else %} --- ✅ System healthy. No recommendations. {% endif %}

      **Metric source**: {% if psi %}🟢 PSI active (CPU + RAM + I/O + Disk) —
      hardware score uses 4 components{% else %}⚙️ Classic sensors (CPU + RAM +
      Disk) — hardware score uses 3 components{% endif %}

```

### HAGHS Pro v1.1 (Command Center)

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

      | Hardware | Application | | **{{ hw }}**/100 | **{{ app }}**/100 |

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

        {% if updates | length > 0 %} {{ updates | length }} update(s) pending:
        {% for u in updates %} &nbsp;&nbsp; • {{ u }} {% endfor %} [→ Open
        Updates]({{ _upd }}) {% else %} ✅ All updates installed {% endif %}

        <hr>

        Database: {{ db_mb | round(1) }} MB {% if db_mb == 0.0 %}*(external DB
        detected)*{% endif %}


        Recorder: {% if keep not in [none, 'unknown'] %}purge active ({{ keep }}
        days){% else %}no purge configured — DB may grow indefinitely{% endif %}


        {{ 'Entity filter active' if filter else 'No entity filter' }}


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
        {% set grouped = expand(z_list) | groupby('domain') %}

        {{ z_count }} zombie(s) across {{ grouped | length }} domain(s)
        {% if z_count > 20 %}*(showing first 20 — {{ z_count - 20 }} more hidden)*{% endif %}

        {% set _ent = '/config/entities' %}[→ Check Entities]({{ _ent }})

        {% for domain in grouped %}
        <details>
        <summary>{{ domain[0] | title }}: {{ domain[1] | count }}</summary>
        {% for item in domain[1] %}
        &nbsp;&nbsp; • {{ device_attr(item.entity_id, 'name') | default('unknown device', true) }} — {{ item.name }}: {{ item.state }}
        {% endfor %}
        </details>
        {% endfor %}
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
Entities that just became `unavailable` or `unknown` are ignored for 15 minutes. This prevents your score from dropping during brief network hiccups or device reboots. After 15 minutes, they count as zombies.

**Can I change the update interval?**
Yes. Go to **Settings > Integrations > HAGHS > Configure** and adjust the update interval (10–3600 seconds). Lower values give faster updates, higher values save resources.

**What happens if a sub-calculation fails?**
HAGHS uses a safety net: if any pillar calculation times out or throws an error, it falls back to a neutral score (100 / no penalty) and logs a warning. The sensor never crashes.

---

## Changelog

### [v2.2.2] - 2026-03-30
* **Feature:** Added optional **Database Size Sensor** override for external databases (MariaDB, PostgreSQL). Configurable in both Setup and Options flow. When set, HAGHS uses the sensor value (in MB) instead of SQLite auto-detection. When left empty, the default SQLite behavior is unchanged. No migration needed, existing installations are unaffected.

### [v2.2.1] - 2026-03-29
* **Bugfix:** Fixed absurd percentage values in hardware recommendations (e.g. "Memory pressure is impacting score (5698.1%)") when a manually configured CPU/RAM sensor reports absolute values (MB/MHz) instead of percent. Values above 100% are now clamped and a warning is logged to help users select the correct sensor.

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

---

**AI Disclosure:** While the architectural concept and logic are my own, I utilized AI to assist with code optimization and documentation formatting.
