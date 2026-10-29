# GR III / IIIx Fit Quality, Oriented Stamp and HDF ADJ Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Deliver the three approved features as locally verified GR III/IIIx test candidates.

**Architecture:** Keep m10v's ISP, state and build ownership. Add a desktop fit-quality layer, a per-exposure stamp orientation adapter and a new independent native ADJ function. The three subsystems have separate file ownership and may be implemented concurrently under dispatching-parallel-agents; shared build integration belongs to the controller.

**Tech Stack:** Node.js >=20 ES modules, Python build tooling, C/ARM, Unicorn, existing web workbench.

**Spec:** `docs/superpowers/specs/2026-10-28-gr3-fit-quality-oriented-stamp-hdf-adj-design.md` (approved by user on 2026-10-28).

## Global Constraints

- Target official GR III 2.10 and GR IIIx 1.60; preserve each CPU/model identity.
- New HDF ADJ option preserves every original ADJ function and does not change assigned slots automatically.
- LUT quality evaluates final quantized matrices and reconstructed curves; software error is not measured camera accuracy.
- Never silently replace source colours, claim CPU LUT as ISP fitting, or rotate/copy the whole frame for stamps.
- Preserve recipe snapshots, RAW ownership, state migration, original IDs, HDF journal and disabled zero-pixel-work path.
- No push, main merge, production deployment or camera write before user validates the new candidates.

## Review Focus

- Two LUT imports finish out of order: old results never replace the later selection (Task 1).
- Forged or stale quality metadata must not authorize different colour parameters (Task 1).
- Camera rotates after exposure while pictures are queued: each stamp keeps its own direction (Task 2).
- A tiny odd-width/stride image must not cause chroma or padding writes outside its valid planes (Task 2).
- An original ADJ function at the table boundary and a persisted new ID after U-mode recall must remain valid (Task 3).

## Task 1: Fit quality and report UI

**Files:** Create `node/gr3-fit-quality.mjs`, `node/gr3-fit-quality.test.mjs`, dedicated web report module/tests as needed. Modify `node/gr3-lut-worker.mjs`, `node/gr3-lut-fit.mjs`, XMP handoff, server fit route and the actual reachable custom-LUT UI. Record referenced source hashes in third-party notices.

**Interfaces:** `fitCube(bytes, filename, options)` preserves `choices.tone/gamut.look/note` and adds versioned `quality` plus provenance. `assessFit({look,target,model,...})` evaluates encoded parameters; approximation creates a separate selected choice with its own hash and report. Report identity binds source, model, sample set and encoded parameters. Persisted configs and build receipts must carry a verified matching report or explicit legacy/unassessed status.

- [x] Add failing behavioral tests for identity, quantization/node expansion, independent sample groups, range rejection, grey/skin regression guard and explicit approximation.
- [x] Run `node --test node/gr3-fit-quality.test.mjs` and observe the missing-feature failures.
- [x] Implement Darkslide-style representation envelope and explicit convergence, GRMod-style guarded candidate selection and neutral/toned-monochrome handling; fixed source hashes/licenses. Keep camera-model/domain limits visible.
- [x] Wire the reachable UI with plan comparison, report details and JSON download; cover XMP unsupported items, tampered parameters, cancellation and late results.
- [x] Run fit-quality, LUT/XMP, custom-film, HTTP and UI tests. Expected: new behaviors pass; any baseline/fixture failures are named separately.
- [x] Commit only Task 1 files and report exact test results.

## Task 2: Per-exposure oriented stamps

**Files:** Modify `native/gr3/m10v_library.c/.h`, capture and recipe/trace ownership modules as required. Add `tests/test_gr3_stamp_orientation.py`; extend existing capture/ARM stamp tests. New build adapter files permitted; coordinate all edits to `scripts/build_gr3_m10v_library.py` with controller.

**Interfaces:** Direction 0..3 is capture-owned, normalized to the official EXIF mapping. `m10v_library_image`/an explicit render context carries transient direction, not persistent film state. Logical stamp coordinates map to original Y/C pixels; zero direction preserves existing layout.

- [x] Add failing native/ARM tests for four directions/four corners, two-line alignment, invalid directions, tiny odd-stride images and delayed processing after rotation.
- [x] Run the new tests and observe wrong placement or missing snapshot failures.
- [x] Verify the official exposure direction chain; freeze direction in explicitly owned recipe storage. Add layout/overlap assertions. Preserve original pixel planes, dimensions, EXIF and state ABI.
- [x] Implement only stamp coordinate transforms; test RAW/disabled paths, invalid time, aliases and padding.
- [x] Run `tests.test_gr3_stamp_orientation`, library/capture snapshot, lifecycle and genuine producer/zero-pixel-work tests. Expected: all changed behavior passes, existing unchanged output remains equal.
- [x] Commit only Task 2 files, or supply exact shared-builder changes to controller if another task needs them.

## Task 3: Independent HDF ADJ function

**Files:** Create `native/gr3/m10v_hdf_adj.c`, `scripts/build_gr3_hdf_adj.py`, `tests/test_gr3_hdf_adj.py`; modify HDF controller/cache adapters as needed. Controller owns final edits to common `scripts/build_gr3_m10v_library.py` and Node verification manifests.

**Interfaces:** A new function ID outside original 0..19 has four values and shares `m10v_hdf_load/save` and published capture cache. Build manifest lists relocated table spans, every reader/length/ID guard, added list rows/resources, patches and capability status.

- [x] Establish official 20-record table plus all construction/read/index/bounds consumers from exact firmware. Add failing tests preserving all old records/functions and accepting the added option.
- [x] Run `tests.test_gr3_hdf_adj` and observe failure for absent independent option.
- [x] Implement complete relocation/length/list/getter/setter coverage, five ADJ selection lists and new resource/icon. No original slot assignment changes; no reuse of 0x09/0x13.
- [x] Add real-controller ARM tests for first/last original function and added function, confirmation/cancel/half-press, save failure, MENU parity, U modes and unknown persisted IDs; keep FS outside per-item drawing and capture.
- [x] Run HDF-menu/shared-HDF/new ADJ plus prior ADJ-exit/queued-exit regression tests. Expected: passed behaviors and no silent mode reset or table overrun.
- [x] Commit Task 3 module files; hand exact common-builder/verification integration to controller.

## Task 4: Integration, review and candidate delivery

**Files:** Common builder/Node independent verifiers/source fingerprints; related manifests, testing notes and updated spec/plan status. Build output goes only into new ignored `builds/` directories.

- [x] Recover read-only official input/cache/venv from main checkout after hashes match; record current main and production identity without mutations.
- [x] Run focused original baseline and retain failure logs before relevant edits; distinguish absent fixtures from regressions.
- [x] Integrate module ownership, resources, entry ordering and recipe offsets. Add tests for actual report/config binding and both-model feature exposure.
- [x] Run `npm test`, relevant Python/ARM tests, genuine producer-to-ISP-to-JPEG and 24MP-unmapped zero-work checks. Compare unrelated failures against exact baseline; never loosen their assertions.
- [x] Fresh whole-branch review against the spec; reproduce important findings as failing tests and fix them.
- [x] Build separate III/IIIx candidates through `scripts/export_gr3_m10v_native.mjs`; verify official hashes, preimages, memory budgets, model/CPU protection and final full-package readback. Produce representative LUT report/approximation evidence.
- [x] Record SHA256, dirty/source/config fingerprints, executed/skipped tests, unresolved device checks, recovery instructions and `WAITING_FOR_USER_VALIDATION`. No deployment.

## Execution result

Local implementation and candidate gates completed; status WAITING_FOR_USER_VALIDATION. Final whole Node run: 387 passed, 40 baseline-reproduced failures, 13 skipped (440 listed cases); post-main-merge download and GR II checks recorded separately. See docs/testing/gr3-fit-stamp-hdf-adj-20261028.md for evidence tiers, exact BIN hashes, separate LUT export path and recovery requirements.
