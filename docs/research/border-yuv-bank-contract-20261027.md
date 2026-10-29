# Original YUV bank allocation study — 2026-10-27

Read-only, hash-pinned original ARM study. No production allocations, descriptors,
RAW fields, firmware builds or pool lifetimes are changed. Numeric results below
use fixture6000×4000, common stride6016, raw-height4000, preview720×480/stride720,
thumbnail160×120. Other shooting modes require their own query and geometry.

## Bank identity correction

The exact recipe vtable at`0x53d0fc90` contains:

| Vtable offset | Original method |
| --- | --- |
| `+0x80` | `0x5350d47c`: size getter, loads`R+0x350+4*id` |
| `+0x70` | `0x5350d7e8`: bank base setter |
| `+0x98` | `0x53510cec`: fills query sizes |
| `+0x9c` | `0x5350db3c`: developed YUV descriptor layout |
| `+0xa0` | `0x53510fa0`: a separate encoded/staging layout |

Public setter **id5** branches to`0x5350d984`, stores base`R+0x304`, then calls
vtable`+0x9c`. Its size is`R+0x364`. Public setter **id4** instead branches to
`0x5350d960`, stores`R+0x300`, and calls`+0xa0`; it is not the developed YUV bank.
A zero-based “bank4” label is ambiguous: use the actual public getter/setter id5
and fields above. Query loop counters do not equal public IDs: the loop starts1
while its destination starts at size index0.

## Native query and footprint

The analyzer executes original query`0x53510cec`, size getter`0x5350d47c`, and
setter`0x5350d7e8(id5)` including virtual dispatch into`0x5350db3c`. Thumbnail
configuration is intercepted to supply160×120. An unrelated encoded-bank query
helper`0x53664c0c` returns0 as a declared fixture boundary; sizes of that unrelated
bank are not evidence. The developed YUV query branch`0x53510e5c` executes its
original arithmetic and is independent of that helper.

Developed YUV capacity is **3 × common stride × raw-height**, yielding
**72,192,000 bytes**. The size query reads stride`R+0x252` and raw-height from
`*(R+0x23c)+4`; it does not obtain capacity from source descriptor width/height.

Original YUV layout`0x5350db3c` uses:

- full visible dimensions`R+0x256/+0x258`, full stride`R+0x252`;
- preview geometry`R+0x25c/+0x25e/+0x260`;
- source guard displacement`9*16*full_stride`;
- preview guard displacement`3*16*full_stride`;
- native64-byte alignment, including an extra64-byte separation from its
  `align64(plane_bytes+64)` plane-area arithmetic.

The exact descriptor-union extent in the fixture is:

| Descriptor | Dimensions/stride | Plane bytes |
| --- | --- | --- |
| `R+0x70` source | 6000×4000 /6016 | 24,064,000 each |
| `R+0xb0` main staging | 6000×4000 /6016 | 24,064,000 each |
| `R+0x90`, `R+0xd0` preview/staging | 720×480 /720 | 345,600 each |
| `R+0xf0` thumbnail | 160×120 /160 | 19,200 each |

These allocations overlap by design. In particular, main staging starts at the
bank base while source starts after its guard; the descriptors do not represent
four independent full planes. The maximum descriptor endpoint is bank base plus
**51,168,064 bytes**; the query capacity leaves **21,023,936 bytes** beyond that
endpoint. This is a descriptor-union calculation, **not proof that all that tail
is unused by every original consumer or scratch owner**.

Appending a separate, disjoint6320×4640 canvas with stride6336 and two full
byte planes needs58,798,080 bytes. Appending after the proven descriptor union
requires total109,966,144 bytes, an increase of37,774,144 over the stock query.
It therefore does not fit the unchanged bank. This calculation excludes any
additional unproved scratch/cache guard reservation.

## Re-layout within unchanged query budget

A geometry-only native ARM fixture sets visible6320×4640 and stride6336, keeping
raw-height4000, then executes the original query/layout. Its descriptor union is
**61,961,024 bytes**; thus that union is smaller than the original72,192,000-byte
budget. The fixture's own query grows to76,032,000 because it changed the common
stride, which is exactly why this is **not** a safe live implementation recipe.
The analyzer preserves the RAW pointer token`R+0x60`, but an unchanged pointer
does not establish unchanged RAW pitch/status or physical safety.

A more promising implementation candidate would reserve the final padded
canvas inside the existing id5 bank, point the still-visible6000×4000 source at
the canvas inner rectangle, preserve original RAW/common geometry, and move
small preview/workspace regions to nonoverlapping positions. Develop would
write directly into the inner canvas using the new YUV output pitch; only
exterior regions would be hardware-filled after producers finish. That avoids
a second full-size copy and separate canvas allocation.

The arithmetic supports studying this candidate, but the original layout method
cannot independently select that YUV pitch: it reads`R+0x252`. It cannot simply
be called with new geometry on a live recipe. Source guard144 rows and preview
guard48 rows, negative/overscan write footprints, crop offsets, per-plane cache
spans, consumer-owned scratch and all native workspace fields must be preserved.
Moving plane pointers without closing those contracts is unsafe. Dimensions for
EXIF rotation variants and alternate border styles need individual capacity and
margin checks; this script does not assert universal fit.

## Producer and consumer pitch evidence

Low public YUV descriptors carry their byte stride at`+0x14`. Existing original
Granulation loads that field at`0x5367af7c` and`0x5367afd0` when constructing its
native format6 descriptors. The original public copy and resize service probes
also propagate low descriptor strides, as documented in the copy/resize studies.
BackResize begins by copying source`R+0x70` to module scratch before applying
its crop geometry; its path is not an independent allocation owner.

**Develop is the important exception to “change the descriptor and consumers
follow it.”** Recipe setup`0x5350eb10` passes the source plane pointers read at
`0x5350eb84/0x5350eb8c` into Develop config`+0x18/+0x1c` at
`0x5350ebc8/0x5350ebcc`, plus status`R+0x1a8` at config`+0x30`.
It does not pass the source low descriptor pointer/stride.

The module constructor`0x53501170..0x5350120c` initializes consecutive32-byte
public image descriptors, the first starting at **module+0x994c**. This types
the local fields exactly:

| Local field | Public descriptor field |
| --- | --- |
| `+0x994c` | format byte |
| `+0x9950/+0x9954/+0x9958` | plane pointers |
| `+0x995c/+0x995e` | visible width/height |
| `+0x9960/+0x9962` | byte stride/cache rows |
| `+0x9964/+0x9966` | ROI x/y |

**`+0x995e` is visible height, not pitch; `+0x9966` is ROI y, not pitch.**
The prospective local output pitch override is`+0x9960`, never`+0x995e`.

Original helper`0x53501910` reads module status through`module+0x9ba8` and copies
status`+0xaa/+0xac` to output stride/cache rows`+0x9960/+0x9962`. With status
`+0xd0` nonzero, it copies status`+0xd4` to ROI y`+0x9966`, and status`+0xd8`
to visible height`+0x995e`. Later instructions`0x53501f28..0x53501f3c` can
update ROI x and visible width from status`+0xda/+0xee` on another flagged path.
The fixture uses realistic stride6016, rows4000, height4000 and ROI0. It then
changes only local output`+0x9960` to6336, leaving status stride6016. The output
geometry becomes `[6000,4000,6336,4000,0,0]` with no original assertion.

### Original final R2Y path and output register proof

The actual final YUV producer is **R2yInterfaceFactory**`0x5366ed3c`, selector
`0x5366edbc(0)`, message`0x00600002`, parameters**module+0x9938**. The module
sends its original setup request at`0x53501f98`. R2Y dispatcher`0x5366f8c4`
selects setup handler`0x5366f498`, which calls the original packer`0x5366dc90`
and pipeline configuration`0x537cfdf8`. The B2R stage is separate: its params
start at module+0x9904 and its outputs are format8 intermediates; do not
substitute its native descriptor encoding for the final public YUV descriptor.

Original R2Y packer`0x5366dc90` consumes the inline output descriptor at params
`+0x14`, exactly module+0x994c. At`0x5366df30` it reads public format1;
`0x5366df58` selects8bits. At`0x5366df68` it reads params`+0x28`, exactly
module+0x9960, and computes native config`+0x4c` as **the same byte stride**
(the original arithmetic multiplies by8 then divides8). The loop
`0x5366df8c..0x5366dfac` copies Y/C/third pointers from params`+0x18/+0x1c/+0x20`
into native config`+0x90/+0x94/+0x98`, followed by additional output banks.

Native output configuration`0x537cb4e8` loads native config`+0x4c` at
`0x537cbbfc` and invokes stride setter`0x537dd334` at`0x537cbc04`. The setter
writes low17 bits at unit register base`+0x144`. The executable fixture runs:

`0x53501910 → local output +0x9960 override → 0x5366dc90
→ 0x537cb4e8 → 0x537dd334`.

For override6336, original native output config stride and register image both
become6336; visible dimensions remain6000×4000, output format stays1, status
stride remains6016, and plane pointer tokens propagate unchanged. Both official
ROMs return with **no assertion**. Unit register addresses point to ordinary
fixture RAM; no hardware register, image plane or DMA is accessed. Auxiliary
configuration/filter storage is explicit zeroed fixture metadata, not a camera
measurement. Queue/thread ownership and full stage execution are not simulated.

This closes the **metadata-to-original-register** pitch path for the candidate
local output override without changing RAW/common status. It does not prove
physical writes, overscan, every branch/parallel output, or all later writers.
At the observed module path, later`0x53501f28..0x53501f3c` stores change ROI x
and visible width, not stride; that is useful static ordering evidence. Choose
the final pre-send boundary after the normal config is built and before the
original R2Y setup request if integrating an independently validated plan.

A source `R+0x70` pitch update is still needed for subsequent consumers, but is
not sufficient by itself. The source plane pointers must be repositioned before
Develop setup loads them; the local final R2Y output stride must be updated in
the same frozen recipe transaction. Full bank/scratch/guard and native owner
lifetimes remain acceptance gates.

## Live B2R/R2Y intermediates: restricted normal stream path

The descriptor-union budget does not establish free memory during processing.
A separate executable fixture now runs **original**`0x5350177c`,
`0x53501910`, their real`0x536a21f0/0x536a22d4/0x536a23c0` metadata setters,
the original plane binding fragment`0x53501f04..0x53501f20`, and both original
packers`0x5363fb6c` (B2R) and`0x5366dc90` (R2Y). Native heap entrypoints are
watched and fail the probe if reached. The fixture maps no image memory.

For this **ordinary stream configuration**, not arbitrary camera modes:

| Object during setup | Executed result |
| --- | --- |
| B2R parameters at module`+0x9904` bytes0..7 | `[1,1,1,1,0,0,0,0]` |
| Four heap format8 descriptors referenced at module`+0x9914/+0x9918/+0x991c/+0x9920` | all three plane pointers remain0 |
| B2R packed native output control`+0x25` | 0; this feeds register bit4 via`0x5374859c` |
| B2R packed RGB plane pointers`+0x38/+0x3c/+0x40` | 0/0/0 |
| R2Y packed native input selector`+8` | 1 |
| R2Y packed RGB input pointers`+0x10/+0x14/+0x18` | 0/0/0 |
| R2Y packed final YUV pointers`+0x90/+0x94/+0x98` | exactly the config output Y/C tokens, third0 |

R2Y's behavior is especially concrete: with parameter byte1 set, original
`0x5366dd10` branches directly to`0x5366dda0`, skipping the entire memory RGB
input descriptor at parameters`+0xa0`. That pointer is0 in the fixture and the
original packer still returns without an assertion or unmapped access. Thus the
fixture does not manufacture RGB memory addresses and then assert nonoverlap.
The native metadata indicates a streamed B2R→R2Y path, with no live format8
bank plane addresses in this configuration. Hardware bus semantics are inferred
from that control/descriptor behavior; physical pipeline activity is not run.

Three differential cases separate backing-bank identity from output planes:

1. Bank base`C+0x10=0x60000000`, output tokens based on`0x60000000`.
2. Bank base alone changes to`0x64000000`; all packed RGB and final YUV pointers
   stay identical to case1.
3. Bank base remains`0x60000000`; only`C+0x18/+0x1c` output tokens change to
   addresses based on`0x64000000`; only final packed YUV output pointers change.

The original fragment`0x53501f04..0x53501f20` binds final YUV pointers from
`C+0x18/+0x1c`, with the original supplied offset, rather than from bank base.
The fixture uses offset0; a nonzero crop/iteration offset needs its own bounds
proof and must not be silently discarded or interpreted as a new-pitch row
index without evidence.

The channel helpers`0x536a21f0`, `0x536a22d4`, `0x536a23c0` are metadata
setters, not workspace allocators. In the main ordinary worker, the explicit
reads of config bank base/capacity are at`0x5350256c/0x53502570`, feeding whole
bank cache post-maintenance`0x53502574` after the three-iteration loop finishes
(`0x53502560`). The helper/packer path issues no native heap allocation.
This narrows the feared RGB-tail collision for the tested stream mode; it does
not prove every original opaque callback, hardware mode or parallel recipe
never owns another bank span.

### Liveness and integration conditions

- Before any producer, preserve the original public id5 base/capacity and the
  original RAW/common stride. Reposition only validated YUV/preview descriptors
  inside independently proved live bank bounds.
- At the final pre-send boundary **`0x53501f98`**, after native local geometry
  and plane binding but before publishing this R2Y setup request, verify actual
  B2R stream flags and zero memory-output planes, R2Y input selector1, normal
  path config`+0x49==0`, final output format1/third0, original visible dimensions
  and validated output planes/stride/ROI. A mismatch is unsupported; do not
  assume the fixture represents it. The R2Y input descriptor pointer need not
  be0 on a real camera because selector1 skips it; zero RGB backing planes are
  a conservative gate for the B2R intermediate descriptors.
- Preserve the exact original crop/iteration offsets and evaluate them against
  the new plane bounds. The ordinary worker executes three iterations. R2Y
  output metadata is shared with its original queued worker; it must remain
  frozen until the corresponding original wait completes.
- On the native layout, source`R+0x70` starts144 rows after main staging
  `R+0xb0` for each full plane. The regions overlap deliberately. Do **not**
  alias their base pointers merely because BackResize later may alias its final
  main image to the cropped source: that later alias is a different phase.
  The planner must retain the source-before/after guard relationship and the
  original preview guards, including all cache/overscan spans.
- During Develop, `R+0x70` is the final YUV producer destination while B2R/R2Y
  RGB controls select the stream path above. Only after its original completion
  may later BackResize consume/crop it. BackResize copies the source descriptor
  into scratch and may replace `R+0xb0` backing with cropped source pointers;
  preserve the original temporal ordering and do not fill canvas padding before
  every producer/consumer that may use guard rows has finished.
- Expanded in-bank layout remains inactive until opaque/alternate-mode paths,
  source/main144-row behavior, native pool lifetime, crop bounds, hardware
  overscan/cache behavior and failure quiescence are validated. An ordinary
  stream-mode gate can restrict support; it cannot justify a universal “the
  tail is free” assertion.

## Reproduction and gates

```sh
/Users/zhaoo/Desktop/code/zhaoo/m10v/.venv/bin/python -m unittest discover -s tests -p test_border_yuv_bank_contract.py -v
/Users/zhaoo/Desktop/code/zhaoo/m10v/.venv/bin/python scripts/border_yuv_bank_contract.py --model gr3 --rtos builds/gr3-extension-validation/official-rtos.bin --output /tmp/gr3-border-yuv-bank-contract.json
/Users/zhaoo/Desktop/code/zhaoo/m10v/.venv/bin/python scripts/border_yuv_bank_contract.py --model gr3x --rtos builds/gr3-border-iip-20261027/gr3x-official-rtos.bin --output /tmp/gr3x-border-yuv-bank-contract.json
```

Both official ROMs are hash-pinned. No pixel planes are mapped; query/layout and
configuration are original CPU metadata work. No pool allocation, physical
readback, camera success, refcount/lifetime closure or production readiness is
claimed. Remaining gates include all bank5 scratch consumers, all Develop branches and real
output-pitch acceptance, guard/overscan behavior, review/cleanup references,
failure quiescence, real pool capacity and physical capture/JPEG behavior.
