# SHD50 / Revolog KOLOR / Pegasus — R1 candidate record

Status: `SUPERSEDED_AFTER_MAIN_MERGE`

The user validated this exact R1 candidate, but GitHub `main` subsequently advanced to `7a40360b361957a441c3ba23b67a5f7e0cb4664f` with overlapping native ISP, resource and build changes. The merged release candidate is R2; this R1 acceptance does not authorize publishing R2.

This record covers the implementation candidate only. It is not a camera acceptance record and does not claim 100% visual restoration before real GR III / GR IIIx output is compared with the accepted previews and references.

## Scope

- Stable film IDs: SHD50 `328`, Revolog KOLOR `329`, Pegasus `330`.
- Targets: GR III 2.10 and GR IIIx 1.60 only.
- SHD50 uses its independent native monochrome ISP profile.
- KOLOR and Pegasus use the ColorPlus 200 native ISP base plus 48 immutable signed modulation fields.
- Each rainbow exposure freezes kind, one of four deterministic variants, phase and strength in the existing 96-byte shot snapshot.
- The spatial layer runs as six ordered native Resize + Granulation passes: Y+/Y−/Cb+/Cb−/Cr+/Cr−.
- Pegasus stays in sensor coordinates. EXIF orientation does not rotate its horizontal beam.
- There is no CPU LUT, CPU RNG, CPU photo-plane access or CPU fallback. Missing identity, invalid descriptor, failed native pass or missing completion rejects before JPEG.
- Offline RAW redevelopment rejects KOLOR and Pegasus because that path cannot authenticate and execute the frozen rainbow stage. RAW-only capture remains stock; RAW+JPEG applies the stage only to JPEG.

## Host and ARM evidence

- 85 immutable runtime resources, `11,796,480` bytes, SHA-256 `3c32368958396c4070ba2e9b5b042018919b3a50e40a7ca52a066619e394c6b7`.
- Existing 37 resources retain their prior bytes and names; the final 48 are the two films × four variants × three components × two signs.
- Focused fit/asset/native/SD compatibility suites pass.
- ARM orchestration verifies four-way freeze, queued immutability, exact six-pass order, sensor-coordinate behavior, workspace reuse and fail-closed handling for every native non-success.
- The Node build audit authenticates every rainbow asset descriptor against its packed address and rejects incomplete manifests.

## Exact candidate identities

Both candidates were generated from the exact official inputs accepted by the repository's built-in SHA-256 gates. The official GRLife compatibility runtime passed its complete integrity manifest before either build.

| Model | Candidate | Bytes | Verified hooks | Candidate SHA-256 |
|---|---|---:|---:|---|
| GR III 2.10 | `builds/rainbow-films-r1-gr3/fwdc239b.bin` | 46,724,444 | 327 | `45e0d71799a2cfe501284359db2a78a2a70074f0444a79b4b4ad2e1af3cd3eaf` |
| GR IIIx 1.60 | `builds/rainbow-films-r1-gr3x/fwdc243b.bin` | 46,852,596 | 326 | `1110d2cd86a22dba6c22ac373d53ab2315dd43eb61e20c630f9ed231ae882d20` |

Shared source identities:

- Runtime source SHA-256: `0d655ccb64dc6d87f2f28c4e13369e8356764198c1366d7e7f0c33b4b596f238`.
- Integration source SHA-256: `f9b25d239c96f95d4e84369ba7a38894116d792d1b818783ba259d776253a958`.
- GR III configuration SHA-256: `fb602c265b2b59371eb411fc1e4fdba054756286fc0b4ec4cc456030ed61666c`.
- GR IIIx configuration SHA-256: `850d99b014b10b3bc084d4ddc60522ab5425c160246fc945e1e19d0ea0a6c7d3`.

Each output directory contains the final BIN, configuration, build receipt, runtime manifest, target relocation coverage and the exact linked runtime. The exporter decoded the final BIN and authenticated the linked runtime, resources, descriptor bindings and hook preimages before writing these packages.

Install archives:

- GR III: `builds/M10V-SHD50-KOLOR-Pegasus-r1-GRIII.zip`, SHA-256 `f3171682d06b331266e461d872092ed4eaea859d29e618078658ef9a0b788c6b`.
- GR IIIx: `builds/M10V-SHD50-KOLOR-Pegasus-r1-GRIIIx.zip`, SHA-256 `1d3428bacf5533f779c3bffbb44e5d8bbc41f7e51a37b424a415071218a3c6ef`.

## Verification status

- GR III delivered pure-ISP candidate: final-BIN identity, runtime assets, SHD50 no-rainbow path, KOLOR/Pegasus six native sensor-coordinate passes, completion bit and JPEG admission pass. The rainbow fixture explicitly models the camera's owned ShootingInfo pool; an unauthenticated identity remains fail-closed.
- GR III and GR IIIx delivered RAW test passes against both final BINs. KOLOR/Pegasus remain excluded from offline RAW redevelopment; RAW+JPEG applies their film stage only to JPEG.
- Focused Node/Python fit, identity, SD compatibility, native asset, rainbow freeze/render, relocation and runtime-interpreter tests pass.
- The broad historical current-pipeline matrix was stopped during its long all-profile ARM loop. Before the stop it exposed pre-existing custom-ISP persistence and Marlboro expectations outside this three-film scope; those results are not counted as candidate acceptance.
- No host test proves physical DMA, native scalar arithmetic, performance or visual equivalence on camera. “100% restoration” therefore remains an acceptance target, not a claim.

## Release gate

GitHub `main`/`develop` and Baota remain unchanged. Publication is allowed only after the user validates the exact candidate SHA/build receipt on the matching camera model. Preview approval and host emulation are not substitutes for that physical-camera validation.
