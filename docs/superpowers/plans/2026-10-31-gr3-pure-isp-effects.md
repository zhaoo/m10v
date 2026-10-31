# GR III / IIIx Pure ISP Effects Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver GR III / IIIx test packages with pure ISP light leaks, grain and blur in the Effects menu.

**Architecture:** Build-time texture generation, native Loader/Scale/LUT/Blend/SPF processing, immutable per-shot settings. No camera CPU pixel processing and no CPU fallback. Existing capture ownership, native completion and export audits remain mandatory.

**Tech Stack:** Python/Unicorn/Capstone analysis; freestanding ARM C and assembly; Node firmware export; original GR III 2.10 / IIIx 1.60 RTOS.

**Spec:** `docs/superpowers/specs/2026-10-31-gr3-pure-isp-effects-design.md` (user approved 2026-10-31).

## Global Constraints

- Only GR III / IIIx; no GR IV or GR II firmware changes.
- No camera CPU generation, decompression, expansion, blur or blending of pixels.
- Never replace real hardware completion with test completion in production.
- Keep source, workspace and graph ownership until actual completion and safe release.
- Preserve all unrelated main behavior and legacy configuration.
- Use current export chain; no push, merge or deployment before candidate acceptance.
- If a hardware contract fails, investigate it before enabling its feature; an unsupported menu is not a deliverable.

## Review Focus

- ROM texture source reaches native DMA without hidden CPU copying.
- Gray/mono scaler accepts the required source format, dimensions and upscaling ratio.
- Timeouts cannot free active DMA resources or permit a second unsafe job.
- Queued frames retain their settings across menu updates and bank reuse.
- Combined effects operate only on the photo, preserve RAW/padding and avoid double processing.

---

### Task 1: Texture transfer and spatial hardware contracts

**Files:** `scripts/border_resize_contract.py`, `scripts/analyze_gr3_pure_isp_effects.py`, `tests/test_gr3_pure_isp_texture_transfer.py`.

**Interfaces:** Extend the existing `probe()` with optional source shape/format/plane and destination stride, preserving current callers. Produce recorded original scaler configuration and explicit assertion/failure evidence, never pixels.

- [ ] Write a failing test for mono ROM-source upscaling to 6000×4000, including failed waits and invalid identity/geometry.
- [ ] Execute the real public resize/worker/configuration route with photo/texture planes unmapped on both models; preserve original assertions.
- [ ] Decode format, address transformation and accepted scaling ratios from the original drivers; reject unsupported paths.
- [ ] Establish new graph planning, submit/wait/release contract before any live installation.
- [ ] Verify with `python -m unittest tests.test_gr3_pure_isp_texture_transfer tests.test_gr3_pure_isp_effects_research -v` and record evidence.

### Task 2: Build-time texture assets and native effect parameters

**Files:** new focused texture generator and native metadata module under `scripts/` and `native/gr3/`, corresponding Python/ARM tests.

**Interfaces:** Immutable resource manifest with dimensions, format, alignment, source hash; versioned global settings and per-shot snapshot. Concrete native interfaces depend on Task 1's demonstrated accepted format, not an invented hardware ABI.

- [ ] Pin deterministic grain statistics, leak masks, bounds and manifest integrity in failing tests.
- [ ] Implement build-time resources; prove container/MMU/DMA addressability independently.
- [ ] Test versioned settings, CRC, failure-atomic save, legacy grain inheritance and zero-effect defaults.
- [ ] Build native metadata code and reject any pixel access from its task callbacks.

### Task 3: Native processing and lifecycle

**Files:** focused native effects module, checked builder hooks, capture snapshot/completion integration and related ARM tests.

**Interfaces:** Frozen resource/parameter selection in the actual recipe; real native completion returned to the existing encoder bridge. All node/driver calls use the contracts demonstrated by Task 1.

- [ ] Write failing actual-ingress tests for queued settings, planning/execution equality, completion mismatch and duplicate stages.
- [ ] Implement texture transfer and grain/leak hardware graphs; never invoke the original CPU RNG.
- [ ] Establish the SPF/Clarity blur response and boundaries; do not reuse HDF's name as evidence of blur.
- [ ] Exercise failed submit/wait/release, active DMA ownership, combinations, RAW and disabled fast paths.

### Task 4: Effects menu and export integration

**Files:** existing HDF/Effects controller and resources; model capability/export modules; menu and Node tests.

**Interfaces:** Three submenus using Task 2 settings, exposed only for demonstrated Task 3 capabilities.

- [ ] Add failing tests for controls, cancel/save/restart, old state, unsupported models and unsupported combinations.
- [ ] Add the approved strength/position/range/size controls and model gates.
- [ ] Preserve existing HDF/border selection, source/config fingerprint and final BIN independent audit.

### Task 5: Regression and identifiable test packages

**Files:** candidate output in a new ignored `builds/` directory; testing notes under `docs/testing/`.

**Interfaces:** Current `scripts/export_gr3_m10v_native.mjs` export and GR IIIx differential port with exact official identities.

- [ ] Run complete `npm test`, relevant host/ARM and real-ingress/no-pixel regressions; compare unrelated baseline failures.
- [ ] Build and independently read back GR III and IIIx packages, preserving release/resource guards.
- [ ] Perform fresh whole-branch review and fix material findings with regression coverage.
- [ ] Deliver candidate hashes, provenance, configuration, installation/recovery and camera checklist; explicitly mark hardware appearance/performance pending.

## Execution authorization

User explicitly requested continued verification and implementation plus test packages. Execute inline in the existing isolated worktree; do not request another plan approval. Any unresolved hardware contract remains a technical blocker, not permission to emit unsafe firmware.

## Execution result

Software implementation and offline candidate validation completed as r7. Separate GR III and GR IIIx packages were generated through the standard exporter, independently audited and reopened to verify archive integrity, model identity and all hashes. Status: WAITING_FOR_USER_VALIDATION.

The original mono shortcut and ineffective Resize rotation field were rejected. The implementation uses real two-plane transfer, prebuilt oriented fields, exact native task ownership, actual callback/wait completion and guarded release. Material review findings (partial JPEG admission, controller/service alias, orientation, ROI, cold/off behavior and stock grain mapping) have regression coverage.

Hardware acceptance remains open: real pixels, phase5 DSP conversion, visual blur/grain/leak quality, physical DMA/cache behavior and performance. These are explicitly distinguished from the completed software contract checks in `docs/testing/gr3-pure-isp-effects-20261031.md`; the original checklist above is retained as the historical plan, not a claim of completed hardware validation.
