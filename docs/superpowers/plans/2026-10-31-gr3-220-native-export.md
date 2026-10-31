# GR III 2.20 native export repair

> **For agentic workers:** Use superpowers:executing-plans to implement and verify each task inline.

**Goal:** Save the default native film configuration from the real uploaded GR III 2.20, preserving that firmware's executable components and version.

**Architecture:** Compile and independently audit the existing runtime against its reviewed reference. Collect typed firmware references during ELF linking and assembly generation. Resolve those references and stock patch sites against the uploaded target, then apply only the resulting patches and relocated private runtime to that target. Unknown or unproved dependencies fail closed.

**Tech Stack:** Node.js, Python, LLVM ARM, Capstone/Unicorn for offline verification.

**Spec:** User's screenshot and save-firmware bug report; source-preservation contract in `docs/testing/gr3-uploaded-source-20261031.md`.

## Constraints and evidence

- Baseline: `ef92d9f39010b4a9cbc681549854275c54e6bdf4`, matching origin/main and successful production DEPLOY_OK in run 41214178656.
- Existing isolated App worktree; preserve other worktrees and all firmware inputs.
- Real official 2.20 input hash: `5c53760b3b564c87239dbf7f5c94d0f6fd91accd156ec4ba672ebfd6b861793e`.
- Do not substitute 2.10 bytes, spoof versions, remove preimage checks, or alter image processing semantics.
- Optional extensions require their own proved references; reject unsupported combinations before declaring ready.
- Offline verification and successful download do not establish camera acceptance. The user subsequently explicitly instructed “没问题就合并main发布github和宝塔”; complete software checks, record the absence of device acceptance and publish under that authorization.

## Review focus

- Repeated/mostly-pointer content windows must not be accepted as unique objects.
- Distinguish instructions, literals, tables and pixel/LUT bytes; never scan arbitrary assets as instructions.
- Account for branch destinations and MOVW/MOVT pairs as well as absolute pointers.
- Prove source identity, non-target component preservation, checksums, version copies and exact configuration on the final downloaded BIN.
- Reject stale preflight, unsupported features, source tampering and incomplete reference coverage.

## Tasks

- [x] Reproduce existing real newer-input HTTP test returning 400 before changes.
- [x] Add typed runtime relocation records with synthetic tests; preserve byte-identical existing builds.
- [x] Resolve real target dependencies with unique code/content/reference witnesses and explicit startup checks.
- [x] Add target export and independent readback, then connect native prepare/build without replacing the upload.
- [x] Run real-input default HTTP export, relevant reference builds, ARM checks, browser download and full Node suite; compare pre-existing failures.
- [x] Produce an identifiable candidate and exact validation limits; see `docs/testing/gr3-220-native-save-20261101.md`.
- [ ] Publish to main/develop and verify GitHub Actions, production and the actual 2.20 export under the user's explicit release instruction.
