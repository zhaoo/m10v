# Third-party notices

The GR III profile and container codec in `m10v_core/profile.py` and
`m10v_core/codec/` are derived from `gr-custom-tool` (DoYitNow), licensed
under GPL-2.0-only. Source file SHA-256 values at import:

`node/firmware.mjs` ports the read-only GR III profile and decoding checks
from those files; it is also covered by this project's GPL-2.0-only license.

- `profiles/gr3.py`: `b5d90aaeaff45531d7f59904ab5eded33a2b5fc2259030c225faf6970c0a0ca7`
- `codec/container.py`: `7f6f83ac21387dd08002a5a0c20fccac6f212e398079c9694304463b6c163a45`
- `codec/frames.py`: `cd89e80080d7e8f1e940b7c737d9d3966ec75fb04a9961b9a1daeb5d19f9b078`

See `LICENSE`. The user's official firmware is not included in this source tree.

## GR IV official-input compatibility and GR II container research

M10V adds an authored `vendor/gr4/gr4_editor/m10v_official_entries.py` compatibility
module and local patches to the vendored `slots.py` and `registry_resources.py`.
They preserve official 1.11.10.7 entry instructions and read its 34-column color
tables through the verified startup RAM mapping, rather than assuming the older
research image's branch wrappers and 37-column ROM tables. Original import hashes
remain in `vendor/gr4/PROVENANCE.json`; local modifications are recorded separately.
These changes retain GPL-2.0-only licensing.

GR II's UNITY encoding facts were investigated using the public
[gr2-boot research](https://github.com/lc2425150/ricoh-gr2-boot-screen-mod), then
independently validated against the user's official image. Its source code was
not copied. M10V's decoder is authored here, including nested containers and the
independently established 512-byte resource-volume offset. See the model-port
research report for exact input hashes and research checkout provenance.

## GRLife compatibility data and local runtime

`web/gr3/film-catalog.json` contains 32 fitted film entries and camera icon pixels
derived from the [public GRLife film catalog](https://grlife.app/firmware-store/film-catalog.js).
Its film fitting data are attributed upstream to `film/NOTICE.md`, including
CC BY-SA 4.0 material; retain the upstream attribution and share-alike
requirements when redistributing that data.
`web/gr3/community-data.json` contains reference recipe values from the public
GRLife community catalog. The user-supplied modified firmware is used for
byte-level regression evidence; it is not distributed in this repository.

The GRLife Python browser core and three JavaScript fitting modules are
downloaded by `scripts/sync-grlife-runtime.mjs` into the ignored `.runtime/`
directory. Each fetched file is pinned by SHA-256 and verified before use.
GRLife source code is not bundled or relicensed by m10v. Users should review
GRLife's applicable license and terms before redistributing a packaged runtime.

The current GRLife runtime manifest SHA-256 is
`1dff66f9e243329ed4ab95b9b7bb4bef74846848f62ae29172d8f3c74574688b`.
Its film-bay extension and film data stay in the ignored local runtime;
m10v's independently written audit reads their pinned hashes and checks the
generated firmware. GRLife separately issues device-bound `FILMS.GRF` files
through its service. m10v does not call that issuer. Its alternative generator
signs plaintext records with a public project key, and its firmware overlay
replaces only the film-bay module's verification public key. This key grants no
access to GRLife's issuer. The original runtime stays hash-pinned and unmodified.

## GR IV reference core

`vendor/gr4/` contains a deterministic source snapshot of the GPL-2.0-only
`gr-custom-tool` distribution by DoYitNow. It includes the Python/native core,
browser source and Lightroom bridge. Three large calibration DNG samples remain local and are excluded from the Git source distribution; their original names and hashes remain in the provenance manifest for restoration. The precise
source commit, every included file hash and size, and intentional exclusions are
recorded in `vendor/gr4/PROVENANCE.json`. The standalone upstream HTTP server and
runtime data are excluded; m10v supplies its own loopback server and product UI.

## Darkslide GR preset metadata

`vendor/darkslide/gr3_v210.json` is copied from LiorMoment/darkslide-gr,
commit `9913169558d725d44400e297ff0bebe2c252abc7`, GPL-2.0-only.
The corresponding license is preserved at `vendor/darkslide/LICENSE`.
The new JS resource reader/editor is implemented in m10v from the GR III
layout, with Darkslide's slot metadata, name storage rules and findings credited.

RAW noise-reduction layout references `idontknownihil/gr3-film-mods`, commit
`04d5d5dd6e85d80089c6200bd0f0de5fff2d658f`; upstream code/notes are MIT.
The new XMP conversion uses the already pinned GPL gr-custom-tool reference
renderer and its Adobe DNG table format decoder, then fits GR III parameters.
It does not reuse GR IV firmware color tables or include an official BIN.

## Ricoh-GRMod digital soft-focus coefficients

The three Q10 coefficient rows in `scripts/build_gr3_digital_hdf.py` reference
`idontknownihil/Ricoh-GRMod`, commit
`16327dbe7bf9e5fd5e4db99ef47237b2240e5487`,
`core/src/fw/clarity.ts` (GPL-2.0, compatible with this project).
The GR III firmware addresses, recipe ownership adapters, settings integration
and audit are independently implemented from the exact GR III 2.10 firmware.
No GR IV executable patch or camera firmware binary is copied into the source.

## GR III power image resource references

The fixed-size shutdown JPEG replacement and A-drive installation approach were
informed by [Darkslide GR](https://github.com/LiorMoment/darkslide-gr),
`darkslide/shared_shutdown.py` and `darkslide/a_shutdown.py` (GPL-2.0-only).
M10V rechecks paths, descriptors and resource slots against its hash-pinned
GR III 2.10 input and implements its own JS container composition and readback.
The independent StartUp JPEG slot is not a GR II BRP patch. No manufacturer's
firmware or JPEG artwork is added to the source distribution.

## Additional film colour references

The C200, Aerochrome 1443, Aerocolor 2460 and VISION3 5203 models use their
individual digitized characteristic and sensitivity data from Jan Lohse's
[spectral_film_lut](https://github.com/JanLohse/spectral_film_lut) (MIT).
The retained license is `third_party/spectral-film-lut/LICENSE`; exact input
hashes and M10V's separate display adaptation are recorded in
`native/gr3/newstocks-reference.json`.

The T-Max 100 display reference comes from
[YahiaAngelo/Film-Luts](https://github.com/YahiaAngelo/Film-Luts), identified
upstream as a G'MIC film LUT. Its MIT license and original cube header are
retained in `third_party/curated-film-luts/`. ProImage 100 uses M10V's manual
reading of Kodak E-4L curves. These are approximate display interpretations,
not manufacturer-supplied transforms or measured camera/film calibration.

## Seven curated style filters (2026-10-23)

Street Monochrome Eerie LUT by Ivan Bogachev (sfi0zy), copyright 2026,
https://github.com/sfi0zy/street-monochrome at commit 3f915315da4f43dd86af304273615b3a54939a94,
licensed under CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/).
Full license and attribution are retained in `third_party/style-filter-luts/`.
M10V changes: neutralisation, resampling to a 15³ lattice, 8-bit quantisation,
and a separate approximate native ISP profile. No endorsement is implied.

Fuji Velvia 50 and Polaroid PX-680 community LUTs are from
YahiaAngelo/Film-Luts at af957b631a304e6be94778b96cb3395de3438e9f, MIT,
copyright (c) 2024 Yahia. The full notice is retained as
`third_party/style-filter-luts/film-luts-license`. PX-680 is a historical proxy,
not a manufacturer calibration for modern Polaroid 600 / i-Type film.

## Noto Sans Bold

`third_party/noto-sans/NotoSans-Bold.ttf` is Noto Sans Bold from the Noto
project, licensed under the SIL Open Font License 1.1. The complete license
and copyright notice are in `third_party/noto-sans/OFL.txt`. The square film
icon PNGs and generated native glyph coverage use this font.

## Noto Sans CJK SC

The pinned card-caption coverage in `native/gr3/m10v_card_captions.json`
is generated from Noto Sans CJK SC Regular, Copyright 2014-2021 Adobe
(http://www.adobe.com/). The source URL
and font SHA-256 are recorded in that file. The SIL Open Font License 1.1
is retained in `third_party/noto-cjk/OFL.txt`. Normal builds use the pinned
coverage and do not download fonts or use host font rasterization.

## Desktop GR III / IIIx fit quality controls (2026-10-28)

`node/gr3-fit-quality.mjs`, `gr3-fit-envelope.mjs` and the fit workbench adapt
ideas and scalar-range checks from the following GPL-2.0 repositories. They do
not contain factory firmware arrays or user LUT files. The existing ignored
GRLife fitter remains responsible for the alternating matrix/curve solver and
CIEDE2000 implementation (its own upstream notices above remain applicable).
The report records the SHA-256 of every numerical model/fitter module actually
used. Validation samples and guarded selection are authored in M10V; upstream
benchmark numbers and camera measurements are not reused.

Darkslide GR, checkout `5f57f6dba7992b537344ae49025846d4c4838b47`
(the newer remote 1.6 UI revision is not claimed as the local source):

- `darkslide/film_fit.py`: `7ff90c8fd1fd0ec1ca4e2efd345619eb46780c21eb13b66b3eff617180a8ded5`
- `darkslide/lut_ranges.py`: `505f7ff92d1a8be29e3cbd2e3861c49b818b092fcfa6b578866d667e89392f84`
- `darkslide/factory_envelope.py`: `2a301918ac77b12132e8cf3f20ce65dc702cb746568b55b02d56fc43e0221731`
- `darkslide/gr3x_factory_envelope.py`: `54e7adc933b6621aafca149c9ec26aec26e3795a17f9c7cc94beb53a263e6919`

Ricoh GRMod, checkout `1f4216e4b80d737a3e670c0b6169398f57598b5e`:

- `core/src/color/gr3x-import.ts`: `d8632de9c5be9e318ea743334d6f6b8b9f96ff1f1ac618e1efdf98c6e53a944b`
- `core/src/color/refine.ts`: `9f58c3f23b1dba3c518b13818b109364244616fb3378a9ac1f81697ebeec6a37`
- `core/src/color/convert.ts`: `3dffd30d6584ead838c92f95f0d356735e45ad8891f6d09866ae59ec0ecf6036`

The native III/IIIx camera model is a Standard display-domain approximation.
GRMod's GR IV 17-node model and its benchmarks are not applied to these models.
The 33-node integer expansion used here is the existing M10V/GRLife film-slot
contract. The factory post-matrix bounds are explicitly schema limits: the
original output matrix has a different encoding and is not a comparable Q512
factory post matrix.
