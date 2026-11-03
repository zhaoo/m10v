# Exact-source anniversary downgrade delivery builder

`node/gr3-anniversary-downgrade.mjs` provides a dedicated two-stage generator for exact public official GR III 2.20 → 2.10 and GR IIIx 1.70 → 1.60. It does not change the ordinary importer, old-version runtime/generator/configuration, or ordinary customization path. User authorization in this session explicitly permits downloadable delivery and publishing before camera tests; that changes delivery timing, not the hardware evidence.

## API

All inputs are Buffers; model is `gr3` or `gr3x`. Input buffers are never modified. All operations are synchronous and suited to the dedicated build worker.

- `prepareAnniversaryDowngrade(newSource, oldSource, model)` returns a `status: ready` plan with source and restore hashes, model, public versions, deterministic `plan_id`, BIN `filename`, ZIP `zip_filename`, and explicit camera-unverified status.
- `buildAnniversaryDowngrade(newSource, oldSource, model)` returns `{candidate, receipt}` after dedicated verification.
- `verifyAnniversaryDowngrade(newSource, oldSource, model, candidate)` returns the receipt, or throws. It does not authorize an unknown candidate or equivalent alternative encoding.
- `exportAnniversaryDowngrade(newSource, oldSource, model, input)` requires exactly two own fields: `accepted_plan_id` matching the current plan, and `acknowledge_instructions: true`. Returns `{zip, receipt, filename}`. The archive contains `stage-1-bridge/fwdc…bin`, `stage-2-official/fwdc…bin`, `receipt.json`, `README.txt`, and `SHA256SUMS`.

`ANNIVERSARY_DOWNGRADE_PROFILES` is a deeply frozen profile map with the four official input hashes, independently reproduced candidate hashes, project/version constants, and file names. Model identifiers in plans and receipts remain `gr3`/`gr3x`; `model_label` supplies display text.

## Exact transformation and checks

The implementation reproduces `scripts/probe_gr3_anniversary_preserved_cpu.py`: preserve combined footer kind 2 and every CPU byte, increase only outer DSP version at `0x38` and RTOS version at RTOS `+0x2038` by 256, replace RTOS `+0x6286cc` `e42103e3` with `e6ffffea`, and repair decoded/container checksums. Outer CPU `0x50` stays unchanged. There are exactly nine changed decoded bytes for each supported input.

Frame replay preserves unaffected compressed frames and replaces changed frames or affected dictionary dependencies with bounded literal blocks. The final original compressed frame is preserved, changing only its four direct decoded-checksum literal tokens. The dedicated verifier authenticates both exact input hashes, checks full header/footer/project/type/padding and checksums, freshly decodes the candidate, compares every decoded byte outside the three allowed ranges, requires the complete expected target including the exact patch values, compares every section header, checks all 131072 CPU bytes and its big-endian checksum, and requires canonical replay equality plus the independent known full-file hash.

The normal `inspectFirmwareImport` continues rejecting these mixed DSP/CPU packages with `version: component copies differ`. Its rule was not weakened. Only this exact-source dedicated verifier admits the specific CPU-preserved candidate.

| Model | Candidate bytes | Candidate SHA-256 |
| --- | ---: | --- |
| GR III | 30509128 | `3860d908a59aea82b0aede7a529bee002a31563605686ed310c75aed5a8615dc` |
| GR IIIx | 30509144 | `6dcd6bb1954f3a316d804d368b47f4e50bfaaca1b54f20b656235b24e76e249a` |

Both hashes were obtained independently by wrapping the existing Python probe's `strict_decode` function to hash its in-memory candidate, then running its existing ARM admission/validator/decompressor-prefix checks. No firmware output was written by that crosscheck. Both Node candidates match these hashes exactly.

## Regression command

```sh
M10V_GR3_220_FIXTURE=/Users/zhaoo/Desktop/fwdc239b.bin \
M10V_GR3X_170_FIXTURE=/Users/zhaoo/Desktop/fwdc243b.bin \
M10V_ANNIVERSARY_PYTHON_CROSSCHECK=1 \
node --test node/gr3-anniversary-downgrade.test.mjs
```

The final complete run passed 9 tests, zero failures or skips, in 72.3 seconds. Cases cover both real fixtures, immutable inputs, exact known candidate hashes, full CPU preservation, retained generic importer rejection, archive content and per-entry hashes, altered sources with repaired sums, swapped/wrong-model inputs, stale or unacknowledged plans, unknown/inherited/symbol export fields, candidate header/footer/project/type/length/padding/checksum corruption, checksum-repaired unrelated RTOS and CPU changes, section-header changes, and alternative encoding of identical decoded bytes. Both independent Python probes run when `M10V_ANNIVERSARY_PYTHON_CROSSCHECK=1`; fixture-dependent tests explicitly skip without their source environment variables.

## Evidence limit

This is file-level production delivery implementation with honest camera-unverified receipts (`camera_verified: false`, `stable: false`). It does not execute physical decompression hardware, complete the original camera parser, Flash erase/write/readback, two-stage camera boot, persistent settings migration, or hardware recovery. No simulated Flash success is introduced. Unknown service firmware remains outside the supported input identity. The official stage-two BIN is a restore update file, not a camera NAND/Flash backup or guaranteed rescue method. Server queue/rebuild/browser download verification and publishing are integrated and reported separately by the coordinating agent.
