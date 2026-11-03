# Firmware preflash safety implementation plan

**Goal:** Implement the conservative read-only checker approved by the user.

**Architecture:** Pin sources before calling any builder. Decode the candidate independently, bind its external digest and receipt, then reproduce the exact candidate using existing generators in temporary storage. Never authorize installation from host evidence.

**Tech stack:** Node built-ins, existing M10V Node/ARM build pipeline, Python source verifier.

**Spec:** `docs/superpowers/specs/2026-11-03-firmware-preflash-safety-design.md`

## Constraints and review focus

- Keep all native/generator/web behavior unchanged; never build anniversary sources in this checker.
- Reject repaired-checksum tampering, a swapped model, stale/missing receipts, a mismatched download digest and third-party camera provenance.
- Correctly identify official IIIx 1.70 as blocked even when full strict decoding is requested.
- A successful host audit always leaves installation blocked; version/provenance is user supplied, not detected hardware.
- Inputs and existing packages remain byte identical.

## Tasks

1. Add failing behavioral tests for the Node checker and IIIx strict source verifier. Use real local official fixtures and integration candidates where available.
2. Add `node/gr3-flash-safety.mjs` and CLI `scripts/check_gr3_flash_safety.mjs`; expose structured checks, reasons and remaining device uncertainty. Regenerate only pinned supported sources and compare all final bytes.
3. Correct `verify_source.py` to use strict structural import for the hash-pinned 1.70 identity while keeping support false. Document commands and limits.
4. Run targeted policy/source/checker tests, build supported default candidates and compare against unchanged main, compare four official binaries, and rerun existing updater/target audits. Record evidence and any failures in the research report. No push, deployment, write-card or camera action.

Execution is local in the existing isolated worktree, branch `daily/firmware-safety-audit`. User approval of the conservative scope applies to this implementation; no further product decisions are introduced.

## Execution record

All four tasks completed locally. Test-first failures demonstrated the missing checker and IIIx 1.70 strict-inventory bug. The detector and corrected inventory passed 35 targeted checks, including both exact real-candidate rebuilds and repaired-checksum RTOS tampering. Both supported default BINs match preserved clean-main outputs byte for byte. Full Node runs have the same 98 failure names on changed and pristine main; see the research report and complete JSON failure inventory. Independent reviewer found no material issues. No existing native/generator files changed; no merge, push, deployment, SD or camera write occurred.
