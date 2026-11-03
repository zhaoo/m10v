# Public GRemote connection and publication

> **For agentic workers:** Use superpowers:executing-plans for integration; independent packaging and UI tasks use focused subagents.

**Goal:** Publish the requested GRemote Android release and approved website; prepare a complete, default-off M10V connection option without widening model or installation gates.

**Architecture:** Keep the existing exact-source, preflight, isolated worker, complete rebuild and download verification. For GR III 2.10 only, a connection-enabled build produces a private ZIP containing its matching fresh-paired SD service. Ordinary GR III/IIIx builds remain BIN downloads. IIIx connection remains unavailable until independently ported and validated.

**Tech Stack:** Node.js, Python ARM build tooling, static browser UI, Flutter Android, GitHub Actions and Baota.

**Spec:** User publication request and `skills/grkit-development/references/release-workflow.md`.

## Constraints

- Exact GR III 2.10 source `d6a3c9c288d784080e7b283222ecdd8752adfeed6faa36dab44f73115354bfd4`.
- Exact GR IIIx 1.60 source `708e79f3b7b96a7e1581b4acf4c412233050a1832718ef7f06c8397db1b431c7`.
- Never reuse GR III bridge addresses on IIIx. Default OFF adds no identity or journal-policy fields to ordinary planner inputs.
- Each connection package has a new private key and instance. No private candidate ZIP, pairing, official BIN or key enters public source/release assets.
- Keep ordinary OFF website configuration-seeding behavior. For enabled connection, expose a separate `gremote_preserve_settings` choice (default true), bind it into identity and map it to the existing preservation policy; reject raw private policy injection.
- Never automatically flash, write SD, enable persistent scripts or clear settings.
- New firmware candidate remains `WAITING_FOR_USER_VALIDATION`; exact-candidate acceptance precedes M10V main/GitHub/production publication.

## Review focus

- Old drafts/model switches cannot enable unsupported bridge; malformed or injected identity requests fail closed.
- ZIP contains matching firmware/service/film metadata and safe manual instructions, not an unusable BIN-only connection toggle.
- Cancellation cleans key-bearing compilation files and does not publish late results.
- A modified result, copied audit JSON or wrong source/configuration cannot pass download proof/browser SHA verification.
- Existing ordinary GR III/IIIx outputs and website/worker/download behavior remain unchanged when OFF.

## Tasks

- [x] Audit remote main and production (`6e77769619ee9dc952e6b3993d052d53e0807a94`), preserve original dirty checkout.
- [x] Build GRemote `1.2.0+19` with established official Android signer; verify checksums, package, version and certificate before release.
- [x] Create and obtain approval for the website visual draft; implement with reciprocal M10V navigation.
- [x] Implement strict default-off switch and deterministic public identity, plus draft/model/option tests.
- [x] Implement private per-download service ZIP and proof/abort/identity tests.
- [x] Integrate checked worker → parent-owned package proof → queue → browser ZIP verification, retaining ordinary BIN path.
- [x] Build exact GR III OFF/ON and IIIx OFF; compare ordinary outputs to base, run applicable Node/ARM/package checks and fresh review.
- [x] Deliver identified private RC2 test candidate with settings preservation and record hardware acceptance limits; do not claim IIIx bridge support.
- [ ] After candidate acceptance, update changelog, fetch/reconcile main, push main/develop and follow Baota deployment to terminal proof.

GRemote publication is independent: its release and approved static site may proceed while new M10V firmware awaits exact-candidate device evidence.
