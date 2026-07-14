# HAGHS Vision & Alignment Rules
- **Core Focus:** HAGHS serves exclusively system health. Features that are purely decorative are treated with low priority or rejected.
- **Local-First & Local-Only at Runtime:** In normal operation the integration is fully
  local. HAGHS's runtime must never depend on external APIs or cloud services, and must never
  initiate outbound network traffic on its own. Every new feature is verified against this: if
  it would introduce an outbound connection during normal operation, it does not ship. The
  only permitted exception is an explicitly opt-in telemetry capability (see "Health
  Telemetry" below) — off by default and never active unless the user consciously enables it.
- **Pragmatism:** The simplest effective solution always wins, followed by a deeper technical explanation. Accuracy is more important than simplicity.
- **Transparency:** All scoring logic must be fully visible in the codebase. No hidden penalties, no obfuscated thresholds.
- **Backward Compatibility:** Score changes between versions must be documented and justified. Users should understand why their score changed after an update. Renaming or removing sensor attributes is a breaking change.
- **Vision of HAGHS:** Short-term: establish HAGHS as the community standard for instance
  health monitoring. Long-term: propose adoption into HA Core.
- **Health Telemetry (optional, opt-in, future):** Separately from the local-only runtime,
  HAGHS may one day offer an *optional* way to contribute aggregated, anonymized health
  metrics, so the wider Home Assistant project can understand how instances are actually used
  and how healthy they are. This is strictly opt-in and off by default; no data ever leaves an
  instance without the user's explicit, informed consent. When implemented, it must be
  aggregated and anonymized, fully transparent about what is sent, and — where possible —
  routed through Home Assistant's own opt-in Analytics rather than a HAGHS-specific endpoint.
  Enabling it never weakens the local-only guarantee of the core integration.
