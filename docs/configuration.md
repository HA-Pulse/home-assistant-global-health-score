[← Back to the README](https://github.com/HA-Pulse/home-assistant-global-health-score/blob/main/README.md)

# Configuration and labels

Setup, every option, external databases, ignore labels, dynamic exclusions, pattern-based ignore and stale reporting in full. The README has the short version.

## Configuration

HAGHS is installed via **HACS** and configured via the **UI**

### 1. Prerequisites

Install the built-in [**System Monitor**](https://www.home-assistant.io/integrations/systemmonitor/) integration via **Settings > Devices & Services > Add Integration** and search for "System Monitor". This is a **native HA integration**, it is not available in HACS.

After adding it, navigate to its entity list and **manually enable** the processor and memory usage entities (they are disabled by default), for example:
* `sensor.system_monitor_processor_use` (Percentage %)
* `sensor.system_monitor_memory_usage` (Percentage %)

> **Note:** Where the Linux kernel provides PSI (usually HAOS and Supervised), HAGHS uses it automatically and these sensors are only a safety net. They are optional in the setup flow; without PSI the System Monitor sensors are suggested when HAGHS finds them, but HAGHS never selects them by itself.
> > **Without PSI and without these sensors:** HAGHS still sets up and keeps running. CPU and/or RAM are left out of the hardware score, a recommendation line says so, and a non-blocking **Repair** in *Settings > System > Repairs* lets you pick the sensors (System Monitor's processor and memory sensors are pre-filled when found). Submitting it includes them without restarting Home Assistant.

**That's it.** Database size and disk usage are detected automatically. No `configuration.yaml` changes needed.

### 2. Installation & Setup
1.  Download **HAGHS** in **HACS** and **Restart Home Assistant**.
> **Note on HACS installation:** Each release attaches a pre-built `haghs.zip` asset (see the GitHub Releases page) that can be downloaded manually and dropped into `<config>/custom_components/haghs/`. HACS itself installs straight from the repository content.
2.  Go to **Settings > Devices & Services > Integrations > Add Integration** and search for **HAGHS**.
3.  Follow the setup mask:
    * Select your **CPU** and **RAM** sensors (smart PSI fallback - only used if PSI data is not available on your host).
    * Choose your **Storage Type** (SD-Card / SSD / eMMC, default: SD-Card).
    * Select one or more **Ignore labels** (multi-select). The `haghs_ignore` label is created automatically and pre-selected.
    * Optionally fill the **Ignore entity-id patterns** field with glob patterns.
    * Optionally select a **Database Size Sensor** for external databases (see the collapsible block below).

### 3. Options Flow (Runtime Settings)
After setup, go to **Settings > Devices & Services > Integrations > HAGHS > Configure** to adjust:
* CPU / RAM sensors
* Storage type
* **Ignore labels** (multi-select)
* **Ignore entity-id patterns** (glob list)
* **Conditional ignore labels** and **Active while (helper)** (both empty by default) - extra ignore labels that apply only while the selected `input_boolean`, `switch` or `binary_sensor` is `on`, e.g. a vacation mode. Set both or neither. See [Dynamic exclusions via automation](#dynamic-exclusions-via-automation).
* **Exclude integration entries from Integration Health** (multi-select, empty by default). Select individual entries by title, domain and entry ID. Other entries from the same integration remain included.
* **Stale threshold** (1–8760 hours, default: 24) - how long a sensor may stay silent before it is reported as stale (see Stale reporting).
* **Stale watch labels** (multi-select, empty by default) - labels whose entities cost points when they are overdue (see Stale reporting).
* **Database size sensor** (for external databases)
* **Update interval** (10–3600 seconds, default: 60s)
* **Zombie grace period** (1–240 minutes, default: 5) - how long an entity must stay `unavailable` / `unknown` before it counts as a zombie. Lower values make detection more aggressive; higher values mask short outages.
* **Battery-class grace period** (1–240 minutes, default: 60) - extended window for entities with `device_class: battery`. Independent from the regular grace; can be set lower if you do not care about that distinction.

Changes apply immediately, no restart required.

### Excluding individual integration entries

If an integration entry is expected to fail while a device is powered off, select that specific entry in **Exclude integration entries from Integration Health**. For example, excluding one ADB entry does not exclude another ADB entry. Entries remain selectable even if setup failed before any devices or entities were created. The entry ID distinguishes entries with the same name.

Excluded entries no longer contribute to Integration Health's unhealthy count, penalty, recommendation or rec_integration_health flag. Other entries still cost 5 points each, capped at 15. Clear the entire selection to include all entries again; the empty selection persists after restart. Removed entries do not cause errors.

This exclusion only affects Integration Health. Zombie and device detection, update checks and Repairs are separate. Area, device and entity ignore labels are not automatically applied to integration entries. HAGHS does not detect intentional power-off or test network reachability.

<details>
<summary><b>External Database (MariaDB / PostgreSQL)</b> - full SQL-sensor walkthrough</summary>

### External Database (MariaDB)

If you use an **external database** (MariaDB) instead of the built-in SQLite, HAGHS cannot auto-detect the database size. To enable database monitoring for your setup:

**1. Create a SQL sensor (no YAML needed):**

Go to **Settings > Devices & Services > Add Integration > search "SQL"** and fill in (see the [SQL integration docs](https://www.home-assistant.io/integrations/sql/) for every field):

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

Credit: [@cryptomilk](https://github.com/cryptomilk) in [#82](https://github.com/HA-Pulse/home-assistant-global-health-score/issues/82).


**2. Select the sensor in HAGHS:**

Go to **Settings > Devices & Services > Integrations > HAGHS > Configure** and select your new sensor in the **"Database size sensor (optional)"** field.

> **Note:** If left empty, HAGHS uses the built-in SQLite auto-detection. Without a sensor HAGHS measures `home-assistant_v2.db` in the config folder; only when that file does not exist is the database part neutral. A leftover SQLite file from before the switch to an external database is still measured. The sensor must report the value in **MB**, not bytes, not GB.

</details>

## Label Configuration (Smart Whitelisting)
To prevent false positives from sleeping tablets or seasonal devices, you have three ways to exclude entities from HAGHS scoring - pick whichever feels most natural:

1. **Disable the entity** (*Settings > Devices & Services > Entity > Disable entity*). HAGHS respects `entity_registry.disabled_by` automatically, so disabled entities never count as zombies or contribute to update penalties. No HAGHS configuration needed.
2. **Apply an ignore label** (described below) for entities you want to keep enabled but exclude from scoring (e.g. vacation devices, tablets that sleep).
3. **Use a glob pattern** (see *Pattern-Based Ignore* further down) for entities without a unique ID, which cannot carry a label.

To use ignore labels:
1.  Go to **Settings > Areas, labels & zones > Labels**.
2.  The `haghs_ignore` label is created automatically during setup. Create additional labels if needed (e.g. `vacation`, `guest_mode`).
3.  Open **Settings > Devices & Services > HAGHS > Configure** and add every label you want HAGHS to honour to the **Ignore labels** field. The field accepts a list, so all listed labels are evaluated.
4.  Assign any of those labels to any **Area**, **Device**, **Entity**, or **Update Entity**.
    * **Pro Tip:** Assigning a label to a **Device** automatically whitelists **all underlying entities** belonging to that specific device.
    * **Area Tip:** An ignore label on an area excludes entities whose effective Home Assistant area is that area. An entity's own area takes precedence over its device's area; entities without their own area inherit the effective device area. Existing entity and device ignore labels remain independent exclusion rules. Area and label changes take effect on the next regular evaluation.
    * **Update Tip:** Labelled update entities are excluded from the update count and penalty.
    * **Note on `hidden_by`:** Hiding an entity from auto-generated dashboards does **not** exclude it from HAGHS. To exclude a hidden entity, disable it or apply an ignore label.

### Dynamic exclusions via automation

Area, device and entity ignore labels do not exclude whole integration entries from Integration Health. Use the separate integration-entry selection in the HAGHS options for that purpose.

**Without Spook: conditional ignore labels.** In the HAGHS options, put a label like
`vacation` into **Conditional ignore labels** and pick a helper (for example
`input_boolean.vacation_mode`) in **Active while (helper)**. While the helper is `on`,
entities, devices and areas with that label are excluded exactly like with a normal
ignore label; when it is `off`, `unavailable`, `unknown` or deleted, they count again.
An automation only switches the helper with a normal Home Assistant action, and HAGHS
updates right after the change. The sensor attribute `conditional_ignore_active` shows
whether the labels currently apply.

```yaml
# Vacation mode on: the conditional ignore labels apply
- alias: HAGHS vacation start
  trigger:
    - platform: time
      at: "08:00:00"
  action:
    - action: input_boolean.turn_on
      target:
        entity_id: input_boolean.vacation_mode
```

**With Spook: switch the label on the entities.** The label actions used below are provided by the
[Spook](https://spook.boo) custom integration. Without Spook, assign or remove the
labels in the UI. List a label like `vacation` in the HAGHS *Ignore labels* field, then
assign/remove it from automations:

```yaml
# Toggle the `vacation` label on a group of entities (requires Spook)
# (use homeassistant.remove_label_from_entity with the same data when vacation ends)
- alias: HAGHS vacation start
  trigger:
    - platform: time
      at: "08:00:00"
  action:
    - action: homeassistant.add_label_to_entity
      data:
        label_id: vacation
        entity_id:
          - light.terrace
          - switch.coffee_machine
          - vacuum.robot
```

For device labels, Spook provides `homeassistant.add_label_to_device` and
`homeassistant.remove_label_from_device` with `label_id` and `device_id` (see the [Spook documentation](https://spook.boo)).

HAGHS picks up the change automatically on its next refresh; no reload needed.

### Pattern-Based Ignore (for entities without a unique ID)

Some integrations create entities without a unique ID. These exist only in the state machine, have no entity-registry entry, and therefore cannot carry a label. When such an entity is `unavailable` or `unknown` past the grace period in a monitored domain, it is reported as *unregistered* (informational only, no score impact, see [Sensor Attributes](https://github.com/HA-Pulse/home-assistant-global-health-score/blob/main/docs/attributes.md)) and never counted as zombies.

Open **Settings > Devices & Services > HAGHS > Configure** and fill the **Ignore entity-id patterns** field with one glob pattern per line. Matching entities are excluded from zombie detection, the unregistered listing and update penalties.

Examples:
- `sensor.docker_*` - every Docker monitor sensor
- `sensor.torque_*` - every Torque OBD sensor
- `binary_sensor.test_?` - `binary_sensor.test_1` through `binary_sensor.test_9`

Wildcards `*` and `?` are supported (standard glob syntax). A malformed pattern does not raise an error; it simply matches literally (e.g. an unclosed `[`), so a single typo never disables the rest of the list.


### Stale reporting

HAGHS checks when Home Assistant last received a state report, not when the value last changed. Passive checks cover only sensor and binary_sensor entities. The default stale threshold is 24 hours; you can set it from 1 to 8760 whole hours in the integration options. A state is a candidate only after this threshold has been exceeded.

The passive list does not affect your score. To opt in to scoring, select Stale watch labels in the integration options and apply one of those labels directly to each entity that must keep reporting. Watched entities can belong to any domain. Device and area labels do not opt entities in. Ignore rules take priority. Each overdue watched entity costs 5 application points, capped at 10 before the configuration bonus. While a watched entity is overdue, the application score cannot exceed 99. These are explicit project rules, not validated failure probabilities.

The sensor exposes stale_candidate_count and stale_candidates for passive findings in sensor and binary_sensor, stale_watch_count and stale_watch_entities for opted-in findings in any domain, stale_penalty for the raw application deduction, stale_threshold_hours for the active threshold, and rec_stale for the watched-entity recommendation. Both lists are sorted and limited to 100 entity IDs; their counts remain complete. Watched entities outside sensor and binary_sensor appear only in the watched list and count, not in the passive list and count. The two entity-ID lists remain visible as current attributes but are excluded from recorder history; the counts remain recorded.

Unknown, unavailable, disabled, ignored and HAGHS-owned entities are excluded from this check. Entities without registry entries may appear in the passive list only if they belong to sensor or binary_sensor, but cannot opt in through entity labels. Old reports are a reason to investigate, not proof of a broken device: quiet integrations and devices can legitimately stop reporting.

Data source: Home Assistant state.last_reported. No recorder queries, external requests or device polling are added.
