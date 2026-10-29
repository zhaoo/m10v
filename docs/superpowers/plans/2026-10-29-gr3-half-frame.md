# GR III Half Frame Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add independent portrait half-frame shots through the existing native aspect pipeline.
**Architecture:** Extend the source-built crop overlay with private identity 6; preserve legacy IDs and compile the feature out for IIIx. Bind a new caption/icon without moving existing resources.
**Tech Stack:** freestanding ARM C/assembly, Python/Unicorn, Node build/composer.
**Spec:** `docs/superpowers/specs/2026-10-29-gr3-half-frame-design.md`

## Global Constraints

GR III 2.10 only. Native ISP cropping, no CPU image pass or RAW pixel access. Existing ratio IDs/resources and persistent state ABI unchanged. No push/deploy before camera acceptance.

## Review Focus

- Invalid crop/quality must leave outputs untouched.
- Old photos and IIIx must retain their previous identities and geometry.
- AF, masked live view, JPEG and DNG must use matching centered geometry.
- Frozen descriptors must survive changing the live menu selection.
- Icon/caption bindings must not shift existing film or HDF resource IDs.

### Task 1: Half-frame native capture and delivery

**Files:** `native/gr3/m10v_aspect*`, new `native/gr3/m10v_half_frame*`, `scripts/gr3_aspect_overlay.py`, native builder/composer/runtime adapter, corresponding aspect tests, candidate builder and testing instructions.

**Interfaces:** Consume existing native ratio/descriptor ABI; produce identity 6 with 2992×4000, 2400×3200, 1680×2240, 960×1280; emit half-frame capability in build receipt and keep IIIx disabled.

- [ ] Add ARM behavior tests for menu cycle, resolution, centered geometry, masked preview/AF, capture identity, MakerNote read/write, DNG and legacy fallbacks; run and observe missing-feature failures.
- [ ] Implement adapters and model gate; run focused Python tests. Expected: all new and old aspect tests pass.
- [ ] Append caption/icon resources; verify final installed native blitter and exact resource readback. Expected: old IDs unchanged, half-frame visible.
- [ ] Build candidate through existing `prepareNative` / `generateNative` with full existing GR3 features; execute relevant capture/ISP/RAW and Node tests. Expected: passing scoped checks; any pre-existing full-suite failures named in report.
- [ ] Audit official identity, every hook/preimage, budget and final container; package separately with hashes and restore instructions. Expected: `WAITING_FOR_USER_VALIDATION`, `camera_tested=false`.
- [ ] Review cumulative diff, record actual checks and commit local feature branch only.
