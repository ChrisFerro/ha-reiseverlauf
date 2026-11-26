---
id: 20261006-pillow-images
status: accepted
migrated-from: docs/development/DECISIONS.md
---

# Draw Images with Pillow and staticmap, Bundle DejaVu Sans

## Context

The export draws a route map, an elevation/speed profile and a composite image for a
photo book. Home Assistant OS runs Python 3.14 on Alpine (musl). Labels are German and English.

## Decision

Charts and the composite image are drawn with Pillow; the map uses `staticmap` with
OpenStreetMap tiles. DejaVu Sans is bundled in `export/fonts/` with its license.

## Rationale

- matplotlib has no musl wheels for Python 3.14 and cannot be compiled on Home Assistant OS
- `staticmap` is pure Python and only needs `requests` and Pillow, both shipped with Home Assistant
- Pillow's built-in font (Aileron) has no umlauts, "Ø" or "–", and Home Assistant OS has no system
  fonts; `env_canada` bundles DejaVu Sans for the same reason

## Consequences

- The package grows by about 760 KB
- `staticmap` raises after three failed tile attempts without shutting down its thread pool; a
  subclass therefore returns a blank tile for missing or broken tiles instead
- Rendering blocks and needs over 100 MB at scale 2, so it must run in an executor
