# Deterministic internal guard component installer

Delivered as a standalone installer helper because private native reservation-acquisition errors and factory teardown liveness remain explicit contracts. The shared central runtime builder and Node export/activation gate are unchanged.

`build_gr3_border_wait_guard.py` compiles native guard C plus ABI adapters, links at the caller-selected address, validates immutable model input and whole touched ABI spans, and returns `(code_bytes, manifest)` with **all18 indivisible native patches**. It does not emit a camera firmware image or install anything on a device.

```python
from scripts.build_gr3_border_wait_guard import build
code, report = build(
    base=next_owned_runtime_address,
    stock=original_rtos_bytes,
    border_enabled=True,
    internal_guard_research=True,
    camera_model='gr3',  # or independently pinned 'gr3x'
)
# Owning runtime builder must append code, reserve/check its address range,
# and merge report['patches'] with conflict/preimage checks.
```

Default `internal_guard_research=False` returns empty code and no patches without reading a firmware fixture, invoking a compiler, creating an output directory or allocating worker tails. Research opt-in requires explicit boolean `border_enabled=True`. Only two independently hash-locked inputs are accepted:

| Model/input | Full RTOS SHA256 |
| --- | --- |
| GR III2.10 | 8a4eafcad2716e0b21e9909264e1242e534f0e39e05cba82a53546ceb4070b67 |
| GR IIIx1.60 | 0f11b0d28bc67932d044c5d01bc0314844a756057c89984278c73a23449a24c6 |

In addition to the full hash, **21 entire ABI/control spans** covering public Resize/Copy/Fill, native client notification/destruction, worker factories/constructors/bodies/dispatchers, IIP service control, lock/event wrappers and driver conditions are checked against fixed byte-identical GR III reference hashes. The manifest records each start/end/hash. GR IIIx admission is an original-code/layout verification, **not physical model support or camera acceptance**.

The helper rejects mutable allocated sections, BSS/TLS, unresolved symbols, unexpected exports, invalid function alignment, out-of-range native BL instructions, unaligned/out-of-bounds component ranges, duplicate patches and input identity changes. Code contains only bounded RX code/constant data; mutable job tokens and CAS storage belong to explicitly enlarged native objects. Each patch records address, original word, replacement word, role and target symbol/address. Root integration must preserve the full allocation+constructor+body+wait+release patch set and reject collisions with other components.

Reproducible component command:

```sh
/Users/zhaoo/Desktop/code/zhaoo/m10v/.venv/bin/python scripts/build_gr3_border_wait_guard.py \
  --border-enabled --internal-guard-research --camera-model gr3 \
  --base 0x54160000 \
  --rtos builds/gr3-extension-validation/official-rtos.bin \
  --out builds/border_recovery/guard-component
```

GR IIIx uses `--camera-model gr3x` and `builds/gr3-border-iip-20261027/gr3x-official-rtos.bin`. Outputs are only `m10v-border-guard-arm.bin` and `m10v-border-guard-arm.json`, never a patched RTOS/camera BIN. Local artifacts for both inputs were generated. At base0x54160000 both code images are **6184bytes**, SHA256 **7856b22dcfa5ad84a4772c10c65772713e190d156d5858853b9d7fff6c94f416**. The reports differ in their independently validated input identity.

## Executed artifact-route verification

```sh
/Users/zhaoo/Desktop/code/zhaoo/m10v/.venv/bin/python scripts/border_recovery_installer.py
```

Nineteen checks pass. They verify default-off isolation, explicit option/model/hash rejection, deterministic code+manifest, all18 patch preimages, source/contract identities, component relocation and code/manifest-only output. Returned patch plans are actually applied to RX original ARM fixtures for **both** GR III and GR IIIx. Each model executes built factory allocation/constructor hooks, original body dispatcher binding/notification, full public Copy outer-stack retention, Fill and Resize parent-frame wait guards, all three Resize DMA shortcuts and a separately relocated private vtable. Hardware operations and kernel/queue boundaries stay explicit; no fake pixels or silicon response is generated.

The installer tests use the helper's actual linked code and returned hook addresses, rather than a separately compiled test adapter. Applying the patch plan again fails preimage checks, preventing accidental double installation or silent override of another component.

## Explicit integration blockers

Manifest `hardware_activation=False`, `pixel_pipeline_enabled=False`, `camera_tested=False` remain fixed. An owning publisher must use a unique live-frame token to hold the worker-owned stage CAS across the complete private Fill/Resize/Transfer frame chain. No native factory Destroy/destructor may reclaim the gate worker while owners or waiters remain. The prototype deliberately retains ownership indefinitely on unrecoverable wait/lock/driver-state failures; a fatal message or deadline cannot free buffers or advance the recipe.

Original reserve/binder routines ignore semaphore wait failures. Existing callback/mask/count checks establish native bookkeeping consistency but cannot retroactively prove a failed acquisition succeeded; private reservation-entry error closure is still a separate requirement. These conditions, actual native teardown quiescence, pixel/cache correctness, memory admission and performance remain activation gates. Packaging this component does not close them or unlock production export.

The inactive bounded Fill bundle entry is included in this code revision; see `border_recovery_fill_bundle-20261027.md`. Its independent header is source-hashed in the manifest. Private clients require76 bytes, maximum132 rectangles per single native enqueue/final callback. The prepared1 whole-canvas cache-ownership prerequisite is an explicit activation blocker.
