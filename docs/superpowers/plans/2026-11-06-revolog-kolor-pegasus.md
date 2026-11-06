# SHD50, Revolog KOLOR and Pegasus ISP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add SHD50, Revolog KOLOR and Pegasus with native ISP color; the two rainbow films also use per-shot varying six-component spatial exposure fields.

**Architecture:** Reuse the existing ColorPlus native frame/multiaxis profile for both film bases, then extend the frozen per-shot ISP-effects snapshot with a tagged immutable rainbow descriptor. Build-host generators create four signed Y/Cb/Cr field variants per film; the camera submits positive/negative component fields through native Resize/Granulation passes and records a distinct completion bit, with no CPU pixel fallback.

**Tech Stack:** Python/NumPy generators and metrics, freestanding C/ARM native ISP adapters, Node catalog/build pipeline, Unicorn/final-firmware regression harnesses.

**Spec:** `docs/superpowers/specs/2026-11-06-revolog-kolor-pegasus-design.md`

## Global Constraints

- Stable IDs 328/329/330 for SHD50/KOLOR/Pegasus, D76/C41/C41 display placement, icons 888/889/890 and captions 1203/1204/1205; preserve all existing identities and the 184-byte state ABI.
- GR III 2.10 and GR IIIx 1.60 only; unsupported models reject the new IDs.
- Camera save path uses native ISP only: no CPU LUT, CPU RNG, mapped photo planes, or CPU fallback.
- Four deterministic variants per film, frozen per exposure; Pegasus is fixed to sensor coordinates.
- Existing leak/grain/blur resources and journal semantics remain unchanged.
- Deliver local test candidates only; no main merge, GitHub push, Actions run, or Baota deployment before user validation.

## Review Focus

- Missing or partial rainbow ISP completion must reject before JPEG without entering legacy CPU LUT indexing.
- The added immutable assets must stay aligned, non-overlapping, below `0x55000000`, and within final firmware space for both targets.
- Queued captures, wraparound generations, repeated Still Make, preview-off and orientation changes must retain their frozen variant.
- Old 85-record FILMS.M10 inputs and all previous resource IDs must remain readable and byte-stable where promised.
- RAW-only/RAW+JPEG, existing configurable leak/grain/blur, HDF, watermark and unsupported-model compaction must retain current behavior.

---

### Task 1: Traceable three-film fit and user preview gate

**Files:**
- Create: `scripts/build_gr3_three_film_preview.py`
- Create: `tests/test_gr3_three_film_preview.py`
- Create: `native/gr3/three-film-reference.json` (generated)
- Create: `docs/previews/three-film-r1/{shd50,revolog-kolor,pegasus,comparison}.png` (generated)
- Modify: `scripts/build_gr3_isp_effect_textures.py`

**Interfaces:**
- Produces: `build_reference() -> dict`, `render_shd50(rgb)`, `signed_fields(kind: str, variant: int) -> dict[str, numpy.ndarray]`, `render_preview(rgb, film, variant)`, preview PNGs, and packed asset names `rainbow_{kolor|pegasus}_{0..3}_{y|cb|cr}_{pos|neg}_nv12`.
- Consumes: existing `_pack_modulation_nv12` alignment/format contract and immutable resource pack generator.

- [ ] **Step 1: Write failing model tests** for SHD50 grayscale/red-response/contrast/highlight shoulder, literal rainbow variant count, signed recombination bounds, Pegasus horizontal band coverage, KOLOR two-dimensional variation, deterministic output, provenance URLs and independent metrics.
- [ ] **Step 2: Run RED:** `python -m unittest tests.test_gr3_three_film_preview -v`; expected failure is the missing module/API.
- [ ] **Step 3: Implement the minimal generator**, produce all previews from `web/gr3/film-street-source.png`, and append compact rainbow assets without changing existing asset bytes or names.
- [ ] **Step 4: Run GREEN:** `python -m unittest tests.test_gr3_three_film_preview -v`; verify generated PNG dimensions/digests and quantitative bounds.
- [ ] **Step 5: Commit** `feat: fit and preview three ISP films`, show the three examples to the user, and pause for visual confirmation before Task 2.

### Task 2: Catalog identities and native base color

**Files:**
- Create: `node/gr3-rainbow-films.test.mjs`
- Create: `tests/test_gr3_rainbow_films.py`
- Modify: `web/gr3/film-directory.json`, `node/gr3-film-directory.mjs`, `scripts/generate_m10v_directory.py`
- Modify: `native/gr3/m10v_library.h`, `native/gr3/m10v_isp_native_look.c`, native/web state and preview modules
- Modify: icon/card/caption generators and generated icon/card/directory assets
- Modify: SD pack compatibility contracts and native build inventory

**Interfaces:**
- Produces: `M10V_SHD50_ID`, `M10V_RAINBOW(id)`, stable resource mappings, catalog entries, an independent SHD50 native profile and KOLOR/Pegasus native look preparation using the existing ColorPlus 200 target.
- Consumes: Task 1 provenance/reference metadata for catalog/build receipts.

- [ ] **Step 1: Freeze the current 85-record SD contract and write failing Node/Python tests** for all three IDs, group order, resource uniqueness, SHD50 profile bounds, rainbow base-profile equality, default effects, reset, unsupported models and old-pack compatibility.
- [ ] **Step 2: Run RED:** `node --test node/gr3-rainbow-films.test.mjs && python -m unittest tests.test_gr3_rainbow_films -v`; expected failures identify missing IDs/resources.
- [ ] **Step 3: Add the two identities and generated assets** without changing existing state layout or rebinding old resources; explicitly reject software-color builds.
- [ ] **Step 4: Run GREEN:** both new test files plus `node --test node/gr3-film-picker.test.mjs node/gr3-sd-film-pack.test.mjs` and `python -m unittest tests.test_gr3_m10v_library.py tests.test_gr3_c41_sd.py -v`.
- [ ] **Step 5: Commit** `feat: register KOLOR and Pegasus C41 identities`.

### Task 3: Frozen rainbow ISP execution

**Files:**
- Modify: `native/gr3/m10v_isp_effects_shot.h/.c`
- Modify: `native/gr3/m10v_isp_effects_pipeline.c`
- Modify: `native/gr3/m10v_isp_effects_render.c/.h`
- Modify: `scripts/build_gr3_isp_effect_render.py`, `scripts/build_gr3_m10v_library.py`
- Modify: `node/gr3-m10v-native-build.mjs`
- Create/modify: focused host-C and ARM tests under `tests/test_gr3_rainbow_isp.py` and existing pure-ISP suites

**Interfaces:**
- Produces: tagged shot-local `rainbow_kind/variant/phase/strength` for IDs 329/330, `M10V_ISP_EFFECTS_NATIVE_RAINBOW`, six signed native passes, strict completion/admission checks and resource manifest evidence.
- Consumes: Task 1 packed textures and Task 2 film identity; existing effect settings/journal remain unchanged.

- [ ] **Step 1: Write failing native tests** for deterministic freeze, successive-generation variation, queued immutability, sensor-coordinate orientation, six-pass completion, workspace reuse, invalid tag rejection, partial-completion rejection and zero CPU plane access.
- [ ] **Step 2: Run RED:** `python -m unittest tests.test_gr3_rainbow_isp -v`; expected failures are missing bit/tag/render behavior.
- [ ] **Step 3: Implement minimal metadata and native renderer changes** with build-time descriptor validation, no runtime allocation and no CPU pixel dereference.
- [ ] **Step 4: Run GREEN:** new tests plus `python -m unittest tests.test_gr3_isp_sd_compatibility tests.test_gr3_texture_performance tests.test_gr3_pure_isp_delivered -v` and native build manifest tests.
- [ ] **Step 5: Commit** `feat: render rainbow films through native ISP`.

### Task 4: End-to-end capture proof and candidate delivery

**Files:**
- Modify: `tests/test_gr3_film_pipeline_current.py`, `tests/test_gr3_pure_isp_delivered.py`
- Modify: web preview/catalog presentation tests as required
- Create: `docs/testing/2026-11-06-rainbow-films-r1.md`
- Create: candidate outputs under a new ignored `builds/rainbow-films-r1-*` directory

**Interfaces:**
- Produces: real producer → frozen color/rainbow → Still Make → completion → JPEG proof and labeled GR III/GR IIIx candidate packages.
- Consumes: Tasks 1–3 complete runtime, FILMS.M10 and build receipts.

- [ ] **Step 1: Add failing end-to-end assertions** for all three IDs, preview-off, first shot after switch, three queued rainbow shots, missing/partial completion, unmapped 24MP planes, RAW boundary and repeated Make.
- [ ] **Step 2: Run RED** against a build with the end-to-end wiring intentionally absent; expected failures identify missing delivered-candidate coverage.
- [ ] **Step 3: Wire final build/export inventories and explanatory web preview**, then generate both model candidates through the existing exporter.
- [ ] **Step 4: Run GREEN and final verification:** targeted tests, full `npm test` with clean-main comparison, relevant Python/ARM suites, final BIN readback, manifest/source/config hashes and `git diff --check`.
- [ ] **Step 5: Commit** `test: verify and package ISP rainbow films`; record status `WAITING_FOR_USER_VALIDATION` and do not publish.

