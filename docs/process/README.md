# Process log

A plain-language record of what was built, in what order, and why. One file per
piece of work, newest at the bottom of the table.

These are written for a human catching up, not for a machine. No jargon where a
plain word will do. Where something went wrong, it says so and says what fixed it.

| Date | Document | What happened |
| --- | --- | --- |
| 2026-08-06 | [Phase 0 - backend foundation](2026-08-06-phase-0-backend-foundation.md) | Built the skeleton that talks to FinEdge and stores what it gets back. Caught and fixed an API key leaking into the logs. |
| 2026-08-06 | [Phase 0 - frontend scaffold](2026-08-06-phase-0-frontend-scaffold.md) | React app with the light/dark theme switcher, verified in a real browser. Phase 0 complete. |
| 2026-08-06 | [Phase 1 - schema discovery and universe](2026-08-06-phase-1-schema-discovery-and-universe.md) | Measured four statement shapes instead of the assumed three, found finance companies are not banks, and loaded all 5,630 companies. |
