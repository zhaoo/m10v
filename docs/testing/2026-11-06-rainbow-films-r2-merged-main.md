# SHD50 / Revolog KOLOR / Pegasus — R2 merged-main candidate

Status: `USER_VALIDATED`

On 2026-11-06, after receiving the exact R2 GR III and GR IIIx packages and hashes below, the user explicitly directed that the latest GitHub state be merged and the result published to GitHub and Baota. The later GitHub update was only the successful deployment/tag for `7a40360b361957a441c3ba23b67a5f7e0cb4664f`; `main` and `develop` did not gain another source commit, so the R2 firmware identities remained unchanged.

R1 was explicitly accepted by the user. Before publication, GitHub `main` and `develop` advanced from `49d63c0d6be9ffbd52e0532a1eec3bd1ed353f60` to `7a40360b361957a441c3ba23b67a5f7e0cb4664f`, adding seven global film imprints and changing the same native ISP renderer, shot snapshot, texture pack, resources and build audit. R2 merges both features without publishing them. Because the runtime and BIN identities changed, R1 camera acceptance cannot be transferred to R2.

## Combined behavior

- Film IDs remain SHD50 `328`, Revolog KOLOR `329`, Pegasus `330` for GR III 2.10 and GR IIIx 1.60.
- The existing global film-imprint resources keep IDs `1203..1210`; the three film captions move to `1211..1213` so no latest-main ID is overwritten.
- Native completion uses separate bits for global imprint (`8`) and KOLOR/Pegasus rainbow (`16`). Both can execute in one exposure without acknowledging the other stage.
- SHD50 remains an independent monochrome native ISP look. KOLOR and Pegasus retain the ColorPlus native base and six ordered Resize + Granulation passes.
- To fit the latest-main immutable 512×304 imprint resources below `0x55000000`, the 48 signed rainbow fields are host-fitted to 32×16 and enlarged by the camera ISP. The packed runtime modulation blob is 11,280,384 bytes, SHA-256 `fd542db7b7ec99fceb8e6bbc2f15578ca5076a0a3ddbed2463ecc8fbead23d23`.
- No CPU LUT, CPU RNG, CPU photo-plane access or CPU color fallback is introduced. Invalid identity, native failure or missing completion still fails closed before JPEG.

## Exact R2 identities

| Model | Candidate | Bytes | Verified hooks | Candidate SHA-256 |
|---|---|---:|---:|---|
| GR III 2.10 | `builds/rainbow-films-r2-gr3/fwdc239b.bin` | 47,510,940 | 327 | `bdba718ddd20c3f955c59dbaf34ee677047a52a715baf5788face962a33b94e7` |
| GR IIIx 1.60 | `builds/rainbow-films-r2-gr3x/fwdc243b.bin` | 47,639,092 | 326 | `a0e37c6e9ddab6bb295d3771ad9e130675ef1194f507bb64ef61770a353803e6` |

Shared source identities:

- Runtime source SHA-256: `2c1eca214551c06dff31df419f4158722806ed48f92918b869d53467849bc501`.
- Integration source SHA-256: `d9fd3e9d6ec64f9949a43afa6373bb3821228fe79f67048d722e492ab499e2a8`.
- GR III configuration SHA-256: `80d7534ccd963a8c2815b71650de1fbacd9616ee9a817ed32ee6620afae9db07`.
- GR IIIx configuration SHA-256: `edda9eccbfc0fedddedb001cd3633be01d2451fff25282bb30b521cd1c76fbdf`.
- Imprint asset SHA-256 remains `adfc792bdf010de0bebde30168b33aed6d228143fbe5f6e8bb8bbf3d1b72936a`.

## Offline verification

- Both official-source exports completed and independently read back the final BIN, runtime, resources, model identity and 327/326 hook preimages.
- Focused rainbow, imprint, renderer, shot, texture and Node build-audit checks pass when their required official RTOS fixtures are available; fixture-dependent tests report the missing local fixture rather than a code assertion.
- The GR III delivered-artifact suite passes 19 of 21 checks. `test_existing_global_effects_migrate_once_without_touching_old_journal` is the previously recorded legacy migration baseline failure. `test_untouched_cold_stock_first_shot_passes_gate_into_original_jpeg_route` is introduced by latest main's fail-closed global-imprint cache contract and is retained rather than silently weakening that contract in this merge.
- Host tests do not prove physical DMA, native scalar output, saved-photo appearance, continuous-shot recovery or performance on either camera.

## Required camera revalidation

Install only the matching R2 BIN. With global film imprint off and leak/grain/blur/HDF off, compare SHD50, KOLOR and Pegasus against the accepted R1 output. Check immediate playback, album view and at least three continuous frames. Then enable one global imprint on KOLOR and Pegasus to confirm both native completion stages compose without a stalled save. Keep the accepted R1 package as the recovery comparison.

This exact R2 identity is authorized for GitHub `main`/`develop` and Baota publication. Any later native, asset, configuration or build-parameter change requires a new candidate identity and another validation cycle.
