# SDD ledger — plan: docs/superpowers/plans/2026-11-06-revolog-kolor-pegasus.md

Baseline: origin/main 49d63c0; `npm test` 594 total / 356 pass / 148 fail / 90 skip. Full output: baseline-node.log; exact failures: baseline-failures.txt.

Ruling: the full Node baseline is red before production changes, primarily from unavailable local firmware/build fixtures and existing expectation drift — proceed with strict targeted RED→GREEN and compare final failure names against this captured baseline — cost if wrong: an unrelated baseline failure could mask a new failure with the same name.

Pre-flight Task 1→2: Task 1 produces three-film reference parameters; Task 2 consumes the SHD50 native target and rainbow provenance. Interface names agree.
Pre-flight Task 1→3: Task 1 produces packed rainbow asset names; Task 3 consumes those names in renderer bindings. Interface names agree.
Pre-flight Task 2→3: Task 2 produces IDs 329/330 and `M10V_RAINBOW`; Task 3 consumes those identities when freezing the descriptor. Interface agrees.
Pre-flight Task 1–3→4: Task 4 consumes all three identities, reference hashes, runtime assets and native completion contract. No conflict found.

Ruling: the plan spells `python`, but this macOS workspace only exposes `python3`; all Python verification uses `python3` — cost if wrong: none, the interpreter and dependency set are identical for this workspace.

Ruling: no community LUT with a traceable input color space, license, and provenance was located for SHD50, KOLOR, or Pegasus; the reference therefore records official/community samples and explicit generated ISP parameters instead of presenting an unverifiable LUT as ground truth — cost if wrong: a later verified LUT may justify a refit.

Task 1 RED→GREEN: the new preview module initially failed import because the existing tetrahedral helper lived in a module with an unrelated optional `colour` dependency. Copied the project's small standalone interpolation routine locally; no interpolation behavior changed.

Task 1 visual ruling: initial KOLOR mean absolute field strength (6.63 DN) was visibly weaker than official samples. Added a >10 DN mean and >60 DN peak regression constraint, then raised the deterministic field gain; final preview shows a clear green/warm/pink gradient without changing the ColorPlus base.

Task 1 verification: 20 Python tests pass (`test_gr3_three_film_preview` + `test_gr3_isp_effect_textures`); repeated preview hashes are stable; runtime pack contains 85 resources, is 11,796,480 bytes, verifies checksums/layouts, and remains within 12 MiB.

Task 1: complete (commits 49d63c0..ee1ad2c, tests: python3 -m unittest tests.test_gr3_three_film_preview tests.test_gr3_isp_effect_textures -v → OK)

Ruling: Task 2's prose says “add the two identities”, but its declared interfaces, global constraints and user request require all three stable identities 328/329/330; implementation registers SHD50, KOLOR and Pegasus — cost if wrong: omitting SHD50 would make the approved three-film feature internally inconsistent.

Task 2 RED→GREEN: catalog/state/SD tests initially rejected IDs 328–330; the native profile test initially lacked the three-film artifact API. The final implementation adds all three identities, independent SHD50 native tone, ColorPlus-native KOLOR/Pegasus bases, model gating, captions/icons, native-only rejection, SD records and the pre-three-film compatibility contract.

Task 2 compatibility ruling: the requested legacy Node/Python suite contains failures already captured in `baseline-failures.txt` (including its stale 30-film/56-hash assertions and missing official firmware inputs). New targeted tests, the existing film-picker test, the real C SD compatibility suite, source syntax checks and `git diff --check` are green; no baseline failure is treated as new evidence.

Task 2 build constraint: native firmware readback cannot run in this worktree because `bin/fwdc239b-gr3-official.bin` and `bin/fwdc243b-gr3x-official.bin` are absent, and a bounded search of local code, Downloads and Codex worktrees found no copies. Candidate generation remains blocked on those private official inputs; no substitute bytes are permitted.

Task 3 RED→GREEN: added an ARM freeze harness before implementation. KOLOR/Pegasus now require the exact recorded-film identity, freeze kind/four-way variant/phase/strength into the existing 96-byte shot tail, reserve a dedicated completion bit and worst-case YUV422 workspace, and reject missing/mismatched identity without a CPU fallback.

Task 3 renderer: the build binds all 48 immutable signed component fields as `[KOLOR|Pegasus][variant][Y|Cb|Cr][positive|negative]`. Runtime execution is six ordered Resize+Granulation native passes in sensor coordinates; every non-success returns invalid output, partial completion is rejected before JPEG, and the builder/Node audit authenticate the 85-resource, 11,796,480-byte pack plus descriptor-to-asset addresses.

Task 3 verification: 33 focused model/asset/native/compatibility tests pass, seven focused ARM renderer/freeze tests pass, the trusted-runtime Node audit passes, Node/Python syntax checks and `git diff --check` pass. Two broader legacy ARM tests still need the absent official RTOS fixtures; an existing special-film encoder test remains baseline-red and is unrelated to the new rainbow path.
