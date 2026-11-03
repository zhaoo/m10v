# GR III main companion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Prepare one auditable latest-main GRIII2.10 candidate retaining App film load and extension control.
**Architecture:** Opt-in existing signed mailbox owner port; preserve current native ISP and exact official input guards.
**Tech Stack:** C/ARM, Python/Unicorn, Node, existing Flutter camera contracts.
**Spec:** docs/superpowers/specs/2026-11-03-main-companion-design.md

## Global Constraints
- Never flash/write SD/reset/publish automatically.
- Preserve latest main and personal configuration, ABI184B/v5/10 slots.
- Exact GRIII2.10 input only; candidate remains2.10.21.27.
- Optional bridge off leaves ordinary build unchanged.

## Review Focus
- Stale focal cache returns unavailable without writes.
- Changed/missing seed receipts do not erase valid upgrade journals.
- Provisional link addresses never survive final image.
- New C41 directory/resources and real ISP lifecycle retained.
- Tampered/missing bridge identity fails exact-rebuild verification.

### Task 1: Main baseline and optional bridge port
**Files:** native/companion/*; native/gr3/m10v_companion*; existing seven native bridge adapters; scripts/build_gr3*; node/gr3-companion-owner.mjs; node/gr3-native-library.mjs; node/gr3-m10v-native-build.mjs.
**Interfaces:** prepareNative/generateNative optional companion_identity with buildId/catalogHash/rendererHash; owner ABI0x6440.
- [ ] Run clean-main source verifier, default build and Node baseline; retain logs.
- [ ] Bring reference companion behavior tests first; run to observe missing behavior.
- [ ] Port minimal hunks using three-way patch, preserve all main additions.
- [ ] Run native owner/transport/protocol/ARM guards, compare ordinary bridge-off build.

### Task 2: Configuration protection and safety reconstruction
**Files:** native/gr3/m10v_library_camera.c; scripts/build_gr3_m10v_library.py; node/gr3-native-library.mjs; node/gr3-flash-safety.mjs; scripts/export_gr3_m10v_native.mjs; focused new tests.
**Interfaces:** preserve_existing boolean opt-in in planner/generator/CLI/manifest/receipt, skipped seed replacement for valid existing journal; source fingerprints and bridge identity enter receipt and exact rebuild.
- [ ] RED: valid existing journal across missing/changed seed; malformed bridge identity rejected.
- [ ] GREEN: conditional compile policy and strict receipt reconstruction, ordinary behavior retained.
- [ ] Test no valid journal initialization and stale/busy/unknown-write rejection.

### Task 3: Matching package and independent review
**Files:** existing companion service/package scripts, App camera catalog assets only if needed; docs/testing handoff; ignored builds output.
**Interfaces:** fresh identity binds main catalog/renderer/source to owner/service/App; existing private pairing retained.
- [ ] Build candidate from exact source, audit partitions/preimages/relocations and exact rebuild.
- [ ] Regenerate current camera catalog/pack/service, compatible APK if needed; hash every artifact.
- [ ] Run full Node suite, compare failures with clean baseline; run selected shared ISP/RAW/Half/C41 regression.
- [ ] Fresh independent whole-change review, fix material issues with RED→GREEN.
- [ ] Deliver identifiable private package with manual backup/install/check procedure, device acceptance pending.
