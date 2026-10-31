# Four ISP Looks Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add 2383, Classic Negative, Classic Chrome and LomoChrome Purple using only native ISP color processing and deliver a GR III test candidate.

**Architecture:** Freeze traceable source transforms and fit them offline to native profiles. Extend existing catalog, per-shot native preparation, Still completion and preview consumers without adding any CPU pixel renderer. Keep other camera models gated.

**Tech Stack:** Python/NumPy/SciPy/colour, ARM C/Clang/Unicorn, Node ESM and existing firmware exporter.

**Spec:** `docs/superpowers/specs/2026-10-31-four-isp-looks-design.md`

**Execution result:** Implemented and independently reviewed; experimental GR III candidate delivered. Exact artifact, source/fit limitations, checks and pending camera acceptance are recorded in `docs/testing/gr3-four-isp-looks-20261031.md`. All four fidelity gates remain false; no production release performed.

## Global Constraints

- IDs 318=2383 (ECN2), 319=Classic Negative (影像), 320=Classic Chrome (影像), 321=LomoChrome Purple (创意).
- Preserve all previous IDs, resource mappings, ten active slots, per-film settings, SD compatibility, borders, Half, HDF, RAW boundaries, and existing effects.
- No CPU color processing for the four new IDs; no per-shot source parsing or full-image allocation.
- The user accepts ISP approximation with disclosed error and physical-camera acceptance; no exact film/camera reproduction claim.
- Production main and successful deployment run 41164474270 both identify `a901016cd4f1ebfe917dbe195d2c5711af9309a1`; keep work local until candidate acceptance.

## Review Focus

- A disabled preview must not disable the per-shot native color cache: Task 3 tests.
- A queued exposure must retain its captured identity after UI selection changes: Task 3 tests.
- An unsupported camera must reject new IDs instead of invoking an old CPU renderer: Tasks 2 and 3 tests.
- A hue-sector seam or neutral ramp must be reported, not hidden by aggregate fit metrics: Task 1 tests and report.
- A legacy SD record must remain readable when inventory expands from 47 to 51: Task 2 tests.

### Task 1: Traceable source transforms and offline native fit

**Files:** Create `scripts/build_gr3_four_looks_reference.py`, `scripts/fit_gr3_four_looks_native.py`, `scripts/verify_gr3_four_looks_reference.py`, `native/gr3/four-looks-reference.json`, `native/gr3/m10v_four_looks_native_profiles.h`, `web/gr3/four-looks-luts.json`, `tests/test_gr3_four_looks_reference.py`, and source attribution in `third_party/four-looks/`.

**Interfaces:** JSON follows extra-films schema: four `stocks` with IDs 318..321, `values` and `native_values` of 10125 bytes, names/keys/title/code/color and source metadata; reference has `native_profiles_full`, hashes and independent errors. Header exports `native_four_looks_frame[4]` and `native_four_looks_hue[4][108]` using the same types as extra-films.

- [ ] Write tests for inventory, source hashes, correct LUT axis/input normalization, profile native bounds and exact header readback; observe failure before implementation.
- [ ] Select and freeze original sources (official Fujifilm 33-grid F-Log2 LUTs, Kodak data/MIT spectral 2383 or authenticated named LUT, licensed Purple community numerical source).
- [ ] Implement `render(film, rgb)` source transform and `generate()`; fit source floats directly with native coefficient constraints, then generate preview tables.
- [ ] Report independent ΔE00 median/P95/max, RGB error, neutral/skin/saturated/seam tests, and separate preview interpolation errors. Run tests and verifier.

### Task 2: Catalog, state, SD, artwork and browser consumers

**Files:** Existing `web/gr3/film-directory.json`, `web/gr3/native-library-state.mjs`, `web/gr3/film-preview.mjs`, `web/gr3/film-picker.mjs`, `node/gr3-film-directory.mjs`, `node/gr3-native-library.mjs`, SD and art generators/consumers and related Node tests. Exclude native C/build code owned by Task 3.

**Interfaces:** Consume Task 1 JSON, retain exact IDs and export only visible 51-entry directory. Source metadata must not leak huge arrays into catalog responses. New film selection must require native GR III pipeline.

- [ ] Extend behavioral tests for exact grouping/names/order, 51 unique visible identities, state persistence, legacy SD compatibility and unsupported-model rejection; observe expected initial failures.
- [ ] Append four identities and wire quantized ISP previews with matching artwork, existing UI behavior and bounded labels. Regenerate derived UI/SD assets using existing scripts.
- [ ] Run relevant catalog, picker, preview, settings, SD, artwork and model boundary tests. No firmware-side CPU implementation.

### Task 3: Native ISP and authenticated capture admission

**Files:** Existing `native/gr3/m10v_library.h/.c`, `m10v_isp_native_look.c`, native SD/recipe/completion/identity/card consumers and build generators, plus `tests/test_gr3_film_pipeline_current.py` and related native tests.

**Interfaces:** Consume Task 1 header. All four IDs use immutable native frames/sectors, actual native completion and zero image-pixel work at the effects-off encoder. Preserve capture ABI and all old profiles.

- [ ] Add failing tests for new IDs in actual producer→Still→completion→encoder chain with pixels unmapped, including live-color disabled and UI change after capture.
- [ ] Extend native identity/resources/profile selection and strict native-only capture guards; never add a color CPU fallback for new IDs.
- [ ] Verify profile bounds, memory/resource budgets, resource identities, SD records, RAW and existing effect combinations; run native/ARM checks.

### Task 4: Integration review and identified test package

**Files:** `docs/testing/gr3-four-isp-looks-20261031.md`, generated local candidate directory and ZIP outside tracked source.

- [ ] Run source verifier and focused suites, then `npm test`; classify preexisting failures with same-main comparison rather than weakening unrelated checks.
- [ ] Build using `scripts/export_gr3_m10v_native.mjs`, audit final candidate and run actual-pipeline tests against that exact candidate.
- [ ] Obtain independent whole-change code review and resolve actionable findings.
- [ ] Record BIN/ZIP SHA-256, build identity, actual checks/skips and per-look fit metrics; deliver camera steps for immediate playback, album and three consecutive shots against stock modes. State that camera acceptance is pending.
