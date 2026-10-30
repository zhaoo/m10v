# Square film artwork implementation plan

> **For agentic workers:** Use independent domain workers for artwork and identity fixes; root integrates web consumers, reviews changes and performs whole-build verification.

**Goal:** Apply approved square classic-pack art to every film display and repair custom/recorded film identity.

**Architecture:** Existing artwork generators remain the source for camera sprites and web assets. Camera identity adapters use journal/custom metadata and photo-recorded identity rather than generic custom fallbacks.

**Tech Stack:** Python/Pillow, freestanding ARM C, Node.js, HTML/CSS.

**Spec:** `docs/superpowers/specs/2026-10-30-square-film-art-design.md`

## Global Constraints

- Do not renumber films, alter LUT/ISP/capture behavior or overwrite user state.
- Keep per-frame/capture paths free of new SD reads and pixel processing.
- Playback must use recorded identity, not live selection.
- Square artwork at both large and compact sizes; no production push/deploy.

## Review Focus

- Imported LUT names in slots 6..10 and legacy names.
- Photograph replay after changing current slots or removing SD pack.
- Compact icons at actual 40px and all sparse film IDs.
- Camera 720x480 card/caption geometry and resource limits.
- Web cached resources, custom dynamic icons and machine consumers.

### Task 1: Identity defects

- [x] Reproduce generic playback and appended custom-name failures with actual ARM/metadata tests.
- [x] Fix native menu/custom-resource and playback metadata/build integration. Preserve unknown-photo handling and old records.
- [x] Run related menu/SD/playback tests and report limitations.

### Task 2: Artwork and camera cards

- [x] Extend real artwork/sprite coverage and card geometry tests for square dimensions and compact legibility.
- [x] Implement shared, distinctive classic packaging designs for the full catalog, generate compact and web assets, update camera large cards/layout.
- [x] Render real-size contact sheets and camera UI preview, run relevant host/ARM tests.

### Task 3: Web consumers and integration

- [x] Audit every current icon consumer, including dynamic LUT names/icons, selectors, slots, settings and other machine consumers.
- [x] Apply consistent square sizing and identity rendering; verify actual UI.
- [x] Review both domain changes, run npm test and relevant Python/ARM suites, export identifiable camera candidate(s), document actual checks, risks and hashes.

Current state: USER_VALIDATED; user requested main/GitHub/Baota publication on 2026-10-30. Results, known baseline failures,
previews and model-specific hashes are recorded in
`docs/testing/square-film-art-20261030.md`. Publication is tracked by the release workflow.
