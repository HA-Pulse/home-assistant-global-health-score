[← Back to the README](https://github.com/HA-Pulse/home-assistant-global-health-score/blob/main/README.md)

# Dashboard cards

Installation, entity ID and the Lite vs. Pro comparison. The card configurations are [docs/cards/lite.yaml](https://github.com/HA-Pulse/home-assistant-global-health-score/blob/main/docs/cards/lite.yaml) and [docs/cards/pro.yaml](https://github.com/HA-Pulse/home-assistant-global-health-score/blob/main/docs/cards/pro.yaml): open the file, copy its content into a manual card (Edit dashboard → Add card → Manual).

## UI Integration

HAGHS provides all data as sensor attributes. Dashboard visualization happens entirely in Lovelace, keeping a clean separation between backend (sensor) and frontend (UI).

Below are two ready-to-use card configurations:

Both configurations are wired to the entity ID `sensor.system_ha_global_health_score`. If your sensor has a different ID (the slug depends on the device and entity name), replace it in two places: the `entity:` line of the gauge card and the `{% set e = ... %}` line at the top of each markdown card.

On older Home Assistant versions (tested: 2024.10) a link to a single entity opens the Entities page, but not that entity's more-info dialog; on current versions (tested: 2026.9 to 2026.11) it opens the dialog directly. All other card links work the same on both.

### HAGHS Lite v1.4 (Quick Check)

A compact card for a fast overview, score, sub-scores, and actionable links.

<img width="492" height="403" alt="HAGHS Lite v1.4 dashboard card" src="https://raw.githubusercontent.com/HA-Pulse/home-assistant-global-health-score/main/docs/images/dashboard-lite.png" />

Configuration: [docs/cards/lite.yaml](https://github.com/HA-Pulse/home-assistant-global-health-score/blob/main/docs/cards/lite.yaml)

### HAGHS Pro v1.4 (Command Center)

A comprehensive dashboard with full score breakdown, grouped zombies, database monitoring, recorder health, and deep-links.

<img width="328" height="1058" alt="HAGHS Pro v1.4 dashboard card" src="https://raw.githubusercontent.com/HA-Pulse/home-assistant-global-health-score/main/docs/images/dashboard-pro.png" />


Configuration: [docs/cards/pro.yaml](https://github.com/HA-Pulse/home-assistant-global-health-score/blob/main/docs/cards/pro.yaml)

### Lite vs. Pro Comparison

| Feature | Lite | Pro |
|---|:---:|:---:|
| Gauge with score | Yes | Yes |
| Hardware / Application score | Table | Table + live formula |
| Calculation failure (failed pillar, failed update cycle) | Status line | Status line |
| Conditional ignore labels active | No | Status line |
| Advisor recommendations (CPU, RAM, I/O, ...) | Inline | Dedicated card |
| Pending updates (by name) | Count + link | Full list + deep-link |
| Stale backup | Status line + link | Status line + link |
| Zombie details | Count by reason + link | Grouped by domain, reason and "for" per entity, breakdown by reason and integration |
| Stale reporting (watched and passive) | Advisor line | Expandable lists with a link per entity |
| Repairs & unhealthy integrations | Count + link | Count + list + deep-link per integration |
| Dead devices (informational) | Count + link | Expandable list, link per device |
| Empty devices (informational) | Count + link | Expandable list, link per device |
| Unregistered entities (informational) | No | Expandable list, link per entity |
| Config-Audit bonus (earned) | No | Yes |
| Database size + warning | No | Yes |
| Recorder health (purge + filter) | Tips + docs link | Yes + docs link |
| Metric source (PSI vs. Classic + component count, CPU/RAM not measured) | Yes (detailed) | Yes (detailed) |
| Deep-links to HA settings | Yes | Yes |
