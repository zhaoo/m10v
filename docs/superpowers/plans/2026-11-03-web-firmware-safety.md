# Web firmware safety implementation plan

**Goal:** Gate every generated firmware download on strict reconstruction and browser integrity, and queue competing jobs instead of rejecting them.

**Spec:** `docs/superpowers/specs/2026-11-03-web-firmware-safety-design.md`

**Architecture:** A bounded single-worker queue covers generation plus verification. A shared server validator issues in-memory download attestations only after exact rebuild and strict inspection; a common egress validates them again. Browser checks precede every firmware Blob download. Camera facts remain declarations.

**Constraints:** Preserve existing native code and firmware bytes; fail closed on missing/invalid evidence; handle cancellation and config changes; keep III2.20/IIIx1.70 blocked. Keep synchronous API consumers behind the same queue. No camera/SD action or production release.

## Tasks

1. Add queue behavior tests, implement bounded queue and cancellation; delegated to isolated file ownership `node/firmware-build-queue*.mjs`.
2. Test and implement server pre-generation camera/source guards, exact rebuilt final candidate audit and unforgeable final-download gate. Wire native, legacy build and backup paths plus asynchronous native job routes.
3. Test and implement browser Blob SHA/receipt verification, provenance form, queue polling/cancel and repeated-download guard. Exercise real HTTP and actual studio handlers; verify mobile layout.
4. Build GR III/IIIx real candidates through HTTP, compare pre-change bytes, run applicable policy/queue/browser/server regressions and a current-vs-baseline full Node comparison. Independent review before delivery.
5. Continue separate downgrade parser/dispatch research only in new probe/test/doc files. Keep hardware evidence gap explicit and webpage downgrade route closed.

Review focus: forged public version/receipt; alternate build routes; async cancellation late results; regenerated image overlays/config binding; retained-result expiry and bounded memory. User approved the strict extra-build cost and queue scope, so execute continuously within this scope.

## Execution result

Tasks 1–4 complete locally. A dedicated Worker thread was added after genuine same-thread integration exposed polling ECONNRESET; it retains the single queue slot through all generation, reconstruction and cleanup. Strict real HTTP builds for both supported models retain their original BIN hashes; queued cancellation and real browser first/repeated download verified. Power-image HTTP overlay verification passed. Final full suite: 549 tests, 398 pass, 98 fail, 53 skip; all98 failure names match pristine main. Independent code review has no findings. No native/generator changes or production release.

Task5 advanced to in-memory complete container formation and real ARM outer/decoded/CPU/dispatch checks, with a demonstrated truncation false positive in the original outer-only check. Complete parsing stops at a hardware decompression boundary; Flash, boot, persistent-state and recovery evidence remain unavailable. Downgrade is not stable and its web entry remains closed. No firmware BIN was emitted by that research.
