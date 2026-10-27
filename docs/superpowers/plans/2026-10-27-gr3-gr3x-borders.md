# GR III / GR IIIx Borders Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add outward Polaroid and film borders without cropping the image or introducing CPU full-image rendering, on GR III and GR IIIx.

**Architecture:** First prove the original IIP graph and extended-dimension contracts against exact official inputs. Only integrate production capture when graph, buffers, preview geometry and failure recovery are established; otherwise continue the bounded offline research and record the precise unresolved gate. Share geometry/settings and preserve model-specific firmware identities.

**Tech Stack:** Freestanding ARM C, Python/Capstone/Unicorn, Node firmware codecs.

**Spec:** `docs/superpowers/specs/2026-10-27-gr3-gr3x-borders-design.md` (user approved 2026-10-27).

## Global Constraints

- Preserve the complete cropped image and add border pixels outside it; never silently resize or crop it.
- No new CPU full-image fill, copy, scaling, or mask generation.
- Both GR III 2.10 and GR IIIx 1.60; exact official inputs, independent identity checks.
- Default off; freeze per shot; RAW unchanged; previews and main JPEG agree.
- Do not activate a hardware graph without bounded ownership, completion and failure recovery.
- No publication before user camera acceptance of identifiable candidates.

## Review Focus

- Large JPEG plus border exceeds current software dimension guards: Task 1 inspects original format writers, encoder, allocation and descriptors rather than changing guards alone.
- Portrait/aspect/focal crop: Task 2 checks full inner rectangle and asymmetric bottom margin at actual cropped dimensions.
- Hardware error after submit: Task 1 checks wait/release semantics; Task 3 must retain storage until proven idle and never report false completion.
- Menu changes while shots are queued: Task 3 verifies immutable settings and geometry identity.
- Preview aliases and RAW: Task 3 verifies distinct ownership, no double processing and matching displayed geometry.

---

### Task 1: Prove hardware composition and extended-size contracts

**Files:** Create `scripts/analyze_gr3_border_iip.py`, `tests/test_gr3_border_iip.py`, `docs/research/gr3-gr3x-border-iip-20261027.md`.

**Interfaces:** `analyze(rom: bytes, model: str) -> dict` accepts only locked official RTOS and emits source hashes, exact original instruction evidence, identified graph/dimension contracts and explicit unproved gates. It never emits firmware or simulates hardware pixels.

- [ ] Restore ignored official fixtures locally from verified existing copies; check GR III and IIIx identities and RTOS parity. Verify linked worktree and current branch.
- [ ] Read original Loader/Store/FreeRect/Blend constructors and native callers, original graph scheduler/wait/release, BackResize sizing and JPEG encoder setup. Trace the actual fields for output dimensions, origin and fill values.
- [ ] Write tests rejecting wrong input hashes/model labels and checking independently established instruction/field observations for both official images; run failing tests before implementing the persistent analyzer.
- [ ] Implement the hash-pinned analyzer with small exact instruction evidence records, avoiding a whole-binary disassembly. Run `python -m unittest tests.test_gr3_border_iip -v` and retain JSON evidence in ignored builds.
- [ ] Record what is proven by executing original ARM and what still requires hardware; no fabricated image output or performance claim. If graph execution or large-output allocation remains unproved, do not enable capture.
- [ ] Commit evidence tooling and report.

### Task 2: Shared border geometry

**Files:** Create `native/gr3/m10v_border.h`, `native/gr3/m10v_border.c`, `tests/test_gr3_border.py`.

**Interfaces:** `int m10v_border_layout(uint32_t style, uint32_t width, uint32_t height, m10v_border_layout_info *out)` returns a complete immutable inner/outer rectangle, aligned margins and bounded hole descriptors; no image pointer or allocation is accepted. It consumes only actual cropped output dimensions, never model focal lengths.

- [ ] Test default off identity, 6000×4000 Polaroid 6320×4640 before hardware alignment, XPan/6×7/small dimensions, portrait layout, overflow and invalid style leaving output untouched. Watch missing API fail before implementation.
- [ ] Implement bounded integer layout and alignment selected from Task 1's verified format contract; asymmetric Polaroid bottom, film holes confined to border. Do not guess hardware alignment if Task 1 has not established it; keep natural geometry distinct from target admission.
- [ ] Run host geometry checks and ARM ABI build appropriate to this isolated module; record that successful geometry does not prove hardware capability.
- [ ] Commit shared geometry.

### Task 3: Integrate only a verified hardware capture route

**Files:** Modify established owners in `native/gr3/m10v_library_capture.c`, `native/gr3/m10v_library_camera.c`, `native/gr3/m10v_settings*`, `scripts/build_gr3_m10v_library.py`, `node/gr3-m10v-native-build.mjs`; exact hook/owner selection comes from Task 1's evidence, not a speculative callback.

**Interfaces:** Consume Task 2's layout and Task 1's verified native owner/graph/dimension contracts. Produce persisted enum 0/1/2 and per-shot geometry/completion handoff shared by both model builds.

- [ ] Before enabling, prove native output allocation, graph scheduling, complete main/preview descriptor propagation and failure quiescence from Task 1. Record any missing contract as a precise implementation gate; never substitute CPU rendering or fake success.
- [ ] Add failing behavior tests for settings migration/confirm/cancel/off, per-shot freeze, no CPU pixel access, preview/RAW ownership, hardware failure and frame-bound completion.
- [ ] Implement menu/resources/storage plus safe hardware route. Off must bypass all new image work; color/spatial effects precede border; existing stamps retain inner-frame coordinates.
- [ ] Run targeted current pipeline/menu/state/ABI tests, then export both models and independently read back protected model words and output identity. Deliver candidate hashes and hardware acceptance checklist.
- [ ] Review entire branch before reporting implementation complete. Do not mark this task done unless both model candidates exist and required checks actually ran.

## Execution record

Use `.superpowers/sdd/2026-10-27-gr3-gr3x-borders/progress.md` for evidence and rulings. User authorized continued execution of the approved design; use inline execution without another permission round for the plan.
