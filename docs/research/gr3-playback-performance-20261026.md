# GR III 2.10 playback/performance investigation — 2026-10-26

Status: **ISP MIGRATION IN PROGRESS; DEVICE SYMPTOMS NOT YET PROVEN FIXED**. The original main investigation below is followed by an explicitly authorized ISP migration.

## Reproduction reported by the user

GR III 2.10: immediate review lacks the selected film effect, album entry takes roughly ten seconds, and bursts can strand a black screen cleared by half-press. 5207/5219 and generally all films reproduce; Kodak Charmera and Pixel World do not. Grain, halo, HDF and both stamps are off. This report is the current device evidence; no current BIN, original JPEG or diagnostic pages were supplied.

## Source identity

Fetched GitHub origin/main on 2026-10-26: `a7c17392296ee01cd3d70e33f19c052cea5b2ac1`. The supplied worktree was clean and already matched that revision. Investigation branch: `daily/gr3-film-playback-performance`.

The latest completed deployment Actions run `40279596800` contains `DEPLOY_OK commit=a7c17392296ee01cd3d70e33f19c052cea5b2ac1 ... service=active`. This confirms that deployment's result, not a fresh SSH reading of the running server or the identity of the user's camera firmware.

## Findings and limits

1. Directory identities matter: 5207 = 66; **5219 = 62**. Both are native ISP capable. 5213 = 298 is a different film, explicitly CPU-rendered in main. An early conversational statement confusing these paths was corrected.
2. The intended normal path is producer snapshot → original Still Make → recipe-specific native completion → zero-work JPEG bridge. Completion requires owner magic/ABI, ShootingInfo, tone, full state bytes and sequence. It must not be replaced by a blanket `completed=1` optimization.
3. If completion is absent, ordinary LUTs still have a full-resolution CPU fallback. The bridge is after resize and processes independent encoded thumbnails, but deliberately does not repaint the original immediate-review buffer (`recipe+0x110`). Thus a fallback can account for slow save and review/color disagreement. **Whether the reported camera actually falls back is not established.** CPU duration can also hold up album entry; slow album entry does not by itself prove slow JPEG decoding.
4. Charmera/Pixel explicitly reject native still-color completion and use their own software renderers. Their success is a useful contrasting case; it does not prove a particular ISP fault or exclude every UI scheduling issue.
5. The final main BIN was executed with the current 184-byte, ten-slot state and authentic stock setup instructions. 5207/5219 at slots 0/4/9 pass real Still Make and real completion matching, then return from the encoder adapter with **24MP image planes unmapped**, without allocation, filesystem loading or image cache operations. There is no mocked completion result. Repeated Make calls do not accumulate color-bank changes. Wrong SI/tone/state cannot claim completion. ISP hardware, DMA and physical scheduling are not emulated.
6. Existing deferred QuickView repair passes original-ARM state-machine checks, including the delivered diagnostic BIN. This proves the specific modeled event ordering is handled, not that the user's black screen uses that ordering.
7. Old `test_gr3_native_fast_capture` fixtures still assume 104-byte/five-slot state. The baseline run ended with 56 failed subtests and one delivered-fixture skip (11 tests total), mainly at the filesystem size assertion before image processing. `test_gr3_isp_recipe_color.library_fragment` also lacks the current `M10V_LEGACY_SETTINGS` definition. These are not passing current-main evidence. New `tests/test_gr3_film_pipeline_current.py` exercises the current ABI and final BIN. Initial new-fixture failures were resolved by initializing the base SI tone as well as its stage1 sub-shot; this was a test fixture correction, not a firmware repair.

## References inspected

- `gr3-film-mods` clean revision `04d5d5dd6e85d80089c6200bd0f0de5fff2d658f`, especially `make_films.py`: native records/curve selection and stock per-mode side-effect neutralization. It is a source reference, not proof of this firmware's runtime behavior.
- https://grlife.app/firmware-store/shop.html : describes native matrix/curve fitting and stock grain, with separate JPEG highlight diffusion. Its own page limits hardware validation. No claim that GRLife demonstrates a validated latency target for M10V; no gated runtime or authentication was bypassed.
- Historical M10V `docs/research/gr3-v9-still-ingress-hdf-2026-10-19.md` records earlier 14–20-second CPU fallbacks caused by a then-wrong context offset. Current main already contains that correction; copying it again would not fix this report.

## Executed validation

- Current-main release-style export: 150 audited hooks; BIN `b8db3756febc37eb3d8bf13871c2d5e7c2493a974b12800299d37c450a3aabab`.
- New current-ABI end-to-end suite: 4 tests passed on that exact BIN and again on the final diagnostic BIN.
- `tests.test_gr3_view_recovery` + `tests.test_gr3_debug`: 24 tests passed.
- Final diagnostic native QuickView ARM probe passed.
- SD pack built and independently audited; packaging hashes/ZIP CRC recorded with delivery.
- Full Python/Node suites were not rerun; no production fix or full regression claim is made. The observed legacy test failures remain disclosed above.

## Next discriminating evidence

The diagnostic is **main behavior with its existing debug/profile capability enabled**, not a speculative performance fix. Its CP pages expose native completion (135), residual stages (138), state source (113), guards (102), dimensions (121/124), and stage timings (150). IO pages expose recipe observation (198), module dispatch and encoder boundaries. Correlate with original JPEG embedded previews and measured immediate-review/album timings.

First collect one failing 5207 shot, one native Positive Film control, and one Charmera control, copying the logs after each group. Then collect a short burst if needed. Each channel retains a bounded tail; absent events cannot establish that they never occurred. Debug SD writes add overhead, so this package cannot certify final release latency. If no CPU fallback is observed, investigate downstream encoder/Store/QuickView ordering rather than disabling ownership checks or guessing at a LUT optimization.

Ordinary films should use a proven pre-resize native path to approach stock responsiveness. CPU-only style/spatial filters require separate quality and capability decisions; silently replacing them with approximate previews would change their output. Final performance acceptance requires same-scene, same-size/NR/card comparisons on the physical camera, with logging disabled. No merge, push, deployment or camera installation was performed.

## GRMod source comparison and authorized migration

Reference: Ricoh-GRMod origin/main `8b4ca5eac085d4acd0464f87539874cc33931751`, fetched 2026-10-26. Source examined, not installed or physically benchmarked.

- `core/src/fw/gr3x/films-r10.ts`: expands three native look tables (tone, multiaxis, YCbCr) from 26 to 84 entries; films 64..83 get immutable tone records. Selected native consumers map their non-color behavior to Standard. This is not a CPU pixel LUT renderer.
- `core/src/fw/gr3x/image-control.ts`: the matrix process hook at `0x536df3e8` installs post-curve coefficients; gamma hook `0x536f028c` installs three 256-entry curves and a per-film identity. Live-change detection `0x536dc998` must retain the actual film identity, not collapse every film to Standard. Its native color is still implemented with hooks, not solely by replacing a table.
- `core/src/color/gr3x-import.ts`: imported cubes are fitted to matrix/RGB curves. The original cube evaluation and firmware approximation are explicitly separate.
- `core/src/fw/gr3x/jpeg-stage.ts` and `tools/halation/halation.c`: halo runs BEFORE JPEG compression on finished YCbCr planes; it allocates CPU work buffers, extracts highlights, box-blurs and loops over output pixels. It is not an ISP hardware halo implementation. Being in the imaging pipeline does not imply ISP execution.

User approved ISP approximation, retaining Pixel World and Charmera's existing special paths. CPU here means full-picture software color processing; computing a bounded ISP coefficient table on the ARM CPU is necessary and is not the forbidden pixel pass.

### Impact and implementation order

| Feature | main | Intended change | Evidence / acceptance |
| --- | --- | --- | --- |
| 5207/5219 and other ordinary supported films | Per-recipe ISP; CPU fallback when completion missing | Keep full per-frame identity; resolve ingress failures before eliminating fallback | Current ABI final-BIN tests pass modeled fast path; reported camera failure still needs attribution |
| 2460, 5213, seven D76 and seven style profiles | Existing live ISP fit, explicit rejection for still | Same fitted ISP color for still and live | New final-BIN test fails for all 16 on main, passes after migration |
| CPU residual stamp/halo pass | Several families always recolor despite completion | Honor authenticated color completion before special LUT branches | Current ABI host test checks unchanged color and padding |
| Pixel World / Charmera | Exact special software renderer | Preserve | Still completion remains absent, even though Charmera has a live approximation |
| Custom SD LUT | Persisted 13x13x13 RGB LUT, CPU renderer | Fit native parameters at import/preparation; cache and freeze with shot identity | Not implemented yet; do not claim all films are native |
| SD format and existing imports | Renderer hash and complete record hashes | Add exact main-era allowlist; keep CRC, reserved bytes and identity checks | Both Node and native C validators must accept old canonical bytes and reject repaired-CRC edits |
| Grain/HDF/halo/stamps/UI/RAW | Existing independent features | Preserve; halo exception accepted | Full feature regression and camera acceptance still pending |

The migration is not evidence that GRMod's table strategy alone fixes this camera's black screen. Do not erase completion checks, fake success, silently skip color, or label the research diagnostic a repaired release.

### Migration verification (2026-10-26)

- Final candidate: `builds/gr3-isp-migration-20261026/fwdc239b.bin`, SHA-256 `fba6d68363cc4b2e481078b88526e2e2342ef43e3f6dabf17989fa415bf59e87`; 150 verified hooks, 32,093,276 bytes, debug disabled. Research candidate, not a verified fix or release.
- 14 tests passed against the extracted final BIN / current source: current pipeline, D76, directory menu and SD compatibility. This includes 92 ordinary-film/parameter cases, all 16 newly native still profiles, rejected wrong frame/state identities, Charmera/Pixel exceptions, repeat Make, no double LUT application, 63 exact old canonical built-in records, custom-record compatibility and repaired-CRC rejection. See `builds/gr3-playback-investigation/isp-migration-tests.log`.
- The new 16-profile test failed on unmodified main with 16 absent native completions before production changes; this is an intentional CPU-path removal, not evidence that it caused the reported 5207/5219 failure.
- Existing Node SD suites: 7 passed / 6 failed both on the working tree and in an independently extracted origin/main archive. Failures include stale directory counts/IDs and an older reconstructed recipe fixture. Baseline log: `builds/gr3-playback-investigation/main-sd-tests.log`. They have not been silently weakened to obtain a green full-suite claim.
- Checked the proposed missing-upload-flag hypothesis against original Still Make and post-Make instructions. No confirming evidence; no speculative flag patch applied.
- `git diff --check` and generated SD contract check pass. No merge, push, deployment or physical camera install.

Still outstanding: actual 5207/5219 delay/black-screen attribution, custom LUT native fitting and immutable runtime handoff, elimination of ordinary-film CPU fallback after its missing-completion cases are correctly handled, physical same-scene performance/color/preview/burst validation. Existing main diagnostic logs remain necessary to distinguish native-ingress fallback from downstream saving/UI delays.
