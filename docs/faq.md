[← Back to the README](https://github.com/HA-Pulse/home-assistant-global-health-score/blob/main/README.md)

# FAQ

Every frequently asked question in full. The README keeps the most important ones.

## Why do I still see zombies or Repairs after excluding an integration entry?

The integration-entry exclusion only changes Integration Health. It does not suppress entity or device detection, update checks or Repairs. Review those findings separately and use their existing exclusion or ignore mechanisms where appropriate.

## How do I hide entities during a vacation without Spook?

Use the **Conditional ignore labels** with a helper such as `input_boolean.vacation_mode`. While the helper is `on`, the labels act as ignore labels; switch it from your vacation automation. Details in [Dynamic exclusions via automation](https://github.com/HA-Pulse/home-assistant-global-health-score/blob/main/docs/configuration.md#dynamic-exclusions-via-automation).

## Can I delete all zombie entities?

No, not without checking them. A zombie only means that the entity has been `unavailable` or `unknown` for longer than the grace period. That also happens during a temporary outage, for an idle device or for an entity that only reports in some operating modes. Check the entity's integration, device and config entry before deleting it; for entities you want to keep, use an ignore label or disable them. With more than 100 zombies, `zombie_count_per_integration` shows which integration they come from. `zombie_reasons` tells you why each one is listed: only `config_entry_missing` is a strong hint of an orphaned entity; `integration_not_loaded`, `not_provided` and `unavailable` are no reason to delete.

## Why is my score so low?
Check the Advisor recommendations in the dashboard card. They tell you exactly where penalties come from (e.g., "5 update(s) pending", "Stale backup detected").

## Does HAGHS send any data to external servers?
No. All data collection is strictly local. HAGHS reads directly from Linux kernel interfaces (`/proc/pressure/*`), `psutil`, and the HA internal state machine. No outbound network traffic is ever initiated by this integration.

## How many people use HAGHS?
The installs badge shows Home Assistant's opt-in analytics ([custom_integrations.json](https://analytics.home-assistant.io/custom_integrations.json), key `haghs`). Only installations whose owners enabled analytics are counted, and most do not. Home Assistant estimates "4-5x more installations than people that opt-in to analytics" ([100,000 installations in analytics!](https://www.home-assistant.io/blog/2021/11/12/100k-analytics/)), so the real number of HAGHS installations is higher than the badge.

## Does HAGHS work with Docker / Kubernetes?
Yes. HAGHS reads disk usage via `psutil` and the database size from the SQLite file or the configured sensor. The Core update entity is detected dynamically, no Supervisor dependency.

## How does PSI work and why does HAGHS use it?
[PSI (Pressure Stall Information)](https://docs.kernel.org/accounting/psi.html) is a Linux kernel feature that measures how long tasks wait for CPU, memory, or I/O, rather than how busy a resource is. HAGHS uses PSI as the primary metric where available, falling back to classic utilization sensors on systems without PSI support. Because their scales differ fundamentally, HAGHS uses separate penalty thresholds for each. When PSI is active, I/O monitoring is also included, giving a 4-component hardware score (CPU + RAM + I/O + Disk). Without PSI, the score averages Disk with the CPU and RAM values that have a sensor selected (1 to 3 components, plus I/O pressure when the kernel provides it). The classic sensors selected during setup are only used when PSI is unavailable.

## I use an external database (MariaDB / PostgreSQL). How do I monitor it?
See [External Database](https://github.com/HA-Pulse/home-assistant-global-health-score/blob/main/docs/configuration.md#external-database-mariadb) for full setup instructions. The sensor must report the database size in **MB**. Without a sensor HAGHS measures `home-assistant_v2.db` in the config folder; only when that file does not exist is the database part neutral. A leftover SQLite file from before the switch is still measured.

## Do I still need a disk usage sensor?
No. HAGHS reads disk usage directly via `psutil`. No manual sensor selection required.

## How are update penalties calculated?
Each update whose offered version HAGHS has seen pending for at least 7 days (also across restarts) costs **5 pts**. A Core version lag (≥3 months behind) adds **20 pts**. The combined penalty is capped at **35 pts**.

## How does the zombie grace period work?
Entities that just became `unavailable` or `unknown` are ignored for **5 minutes by default**, configurable in the Options Flow from 1 to 240 minutes. This prevents your score from dropping during brief network hiccups or device reboots. Battery-class entities (`device_class: battery`) get a separate, longer window (default 60 minutes).

## Why is my score capped at 99 right after a restart?
A cap at 99 means a zombie, an open repair or an overdue watched entity is reported; the Config-Audit bonus can never lift it to 100. A restart itself does not create zombies: HAGHS uses `max(last_changed, boot_time)` as the floor for the grace window, so states restored from the recorder still get the full grace window, and zombie detection waits for `EVENT_HOMEASSISTANT_STARTED` before its first run.

## Do I need to remove and re-add HAGHS after an update?
No. Config entries of every older version (1.x, 2.x, 3.0–3.3) are migrated to the current layout automatically on the next restart, also for users who saw the *"Migration handler not found"* warning on v2.2.x (#75).

## Why did my score change after an update?
The [release summaries](https://github.com/HA-Pulse/home-assistant-global-health-score/blob/main/docs/changelog.md) list the behavior changes per release; v2.3.0 and v2.4.0 include upgrade notes. The recommendations and `rec_*` flags show which factors cost points right now.

## A pending update from yesterday is in the list but doesn't change my score yet. Why?
Because of the 7-day update grace period. The list is informational and shows every pending update that is not ignored or disabled; the **score** only deducts after HAGHS has seen that version pending for at least 7 days, also across restarts.

## Can I change the update interval?
Yes. Go to **Settings > Devices & Services > Integrations > HAGHS > Configure** and adjust the update interval (10–3600 seconds). Lower values give faster updates, higher values save resources.

## What happens if a sub-calculation fails?
HAGHS wraps the whole update cycle in a safety net: a pillar that fails or times out (time limit 10 seconds) falls back to a neutral score (100 / no penalty) for that refresh and the failure is logged, so the sensor keeps updating. If a failure happens outside the two guarded pillars, the **last valid result is kept** instead, and only before the first successful update is a fully neutral result returned.
