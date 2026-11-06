# SHD50 / Revolog KOLOR / Pegasus — R1 candidate record

Status: `BLOCKED_MISSING_OFFICIAL_FIRMWARE`

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

## Candidate generation blocker

The repository does not contain the two private official inputs required by the exact-source build and readback gates:

- `bin/fwdc239b-gr3-official.bin`
- `bin/fwdc243b-gr3x-official.bin`

Both candidate commands stop with `ENOENT` before any output is written:

```sh
M10V_PYTHON=.venv/bin/python node scripts/export_gr3_m10v_native.mjs --pure-isp-effects --model=gr3 builds/rainbow-films-r1-gr3
M10V_PYTHON=.venv/bin/python node scripts/export_gr3_m10v_native.mjs --pure-isp-effects --model=gr3x builds/rainbow-films-r1-gr3x
```

No substitute firmware bytes are allowed. After the exact official inputs are supplied, regenerate both candidates, run final BIN/receipt/runtime readback and the delivered pure-ISP suite, then provide the labeled packages for physical-camera validation.

## Release gate

GitHub `main`/`develop` and Baota remain unchanged. Publication is allowed only after the user validates the exact candidate SHA/build receipt on camera. Preview approval is not a substitute for that physical-camera validation.
