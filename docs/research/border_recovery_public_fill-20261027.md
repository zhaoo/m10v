# Public Fill ABI and native worker readiness, 2026-10-27

Offline original ARM evidence only. The existing 18-patch installer and production
sources are unchanged. No public-call adapter is enabled or added to the build:
factory teardown lifetime and private reservation-acquisition failures remain
activation blockers. No pixels, registers, DMA or physical cameras are emulated.

## Exact public entry

`0x534abc18` can be declared for ABI purposes as:

```c
/* Return register is not a documented status; do not infer success from it. */
void native_fill(void *client, const void *destination_descriptor,
                 uint32_t y, uint32_t cb, uint32_t cr, uint32_t prepared);
```

AAPCS places client/destination/Y/Cb in r0/r1/r2/r3, Cr at entry SP,
prepared at entry SP+4. Public code loads Cr as uint16 at fp+4 and prepared
as uint8 at fp+8 (`534abc30/40`). All three constants are stored as halfwords,
so the native ABI truncates to 16 bits. An actual border caller should validate
its desired sample range before this call; these tests use distinct large
values only to prove placement, not sample calibration.

`prepared != 0` skips `534ab1a4` before dispatch and `534ab60c` afterwards.
This flag is not a cancellation/ownership lease. For prepared=0 those original
pre/post functions execute. The inactive client route uses prepared=1 only
under the external prerequisite that the native descriptor/cache ownership is
already established. This research does not newly establish that prerequisite.

At `534abc60..8c`, parameters at fp-50 contain destination pointer at+0,
Y/Cb/Cr halfwords at+4/+6/+8. The job at fp-44 contains native job vtable at+0,
client at+4, parameter pointer at+8, opcode `010e0004` at+0xc and cookie0 at+10.
The public code gets FrameOperationPipeFactory at `53658a68`, chooses first
worker+4, dispatches to worker+8 through `534aad6c`, and waits client+4/mask10.
Both parameter/job structs live on the original public stack until this wait
returns, so an unguarded wait error cannot be treated as completed work.

Original `5365900c` loads these constants at `536590c0/c4/c8`, stores them in
lower Fill packet+1c/+1e/+20 at `536590dc/e0/e4`, then calls `53769a78`.
The lower service retains order into GPC config planes at+20/+30/+40 and each
plane constant at+44. The ordered sample names are supported by the stock
color path: `534c8d64` gets packed samples via `536c938c`, extracts low byte,
byte1, byte2 and calls public Fill (`534c8dd0`). Table `53dbb15c` contains neutral
black `00 80 80` and white `ff 80 80`. Conversion `536c9450` uses low byte as
base luminance, subtracts128 from byte1/byte2, adds byte2*1.402 to red and
byte1*1.772 to blue, with green coefficients0.344/0.714 (literal floats at
536c9550..60). Thus arguments/planes are Y, Cb, Cr in that order. This is a
native color convention and does not prove JPEG white level or camera output.

## Completion and client lifetime

OnMessage `5365935c` processes opcode010e0004, calls FillRectIip at536594a0,
then at536594a4/ac delivers event03070004 through original client vtable+8.
Native notify `534aab0c` maps precisely this event to client+4 event mask10
(`534aab60..78`). Our existing private notify calls native notify and clears
pending only after it returns. Callback-inflight must also become0 before
client teardown. Neither event reception alone nor outer wait result proves
hardware quiescence; installed inner wait and pre-release gates retain owners.

Native client constructor `534aacc8` writes the original vtable, constructs
event at+4 via536a9bf8, creates it via536aa3a4; native client occupies32 bytes.
Destructor534ac164 restores native vtable and deletes event via536aa34c.
Deleting destructor534ac18c additionally frees the object and must never be
used for an embedded or stack client. Stock wrapper534c8db0 constructs its
stack client, calls Fill, destroys at534c8dd8. An owned private client replaces
the notify vtable slot but retains the actual constructor/destructor sequence;
its larger storage must outlive pending+inflight, not just enqueue.

## Initialization is a separate native phase

Getters only create static factory objects, not workers:

| Factory | Getter | Static object / guard | Required worker |
|---|---|---|---|
| FrameOperationPipe |53658a68|5536327c /55363278|factory+4|
| TransferRect |5369a0e8|5536c00c /5536c018|factory+4|
| Resize |53672c48|5536bf5c /5536bf6c|factory+0xc|

Each factory vtable+8 points to its real create method: Fill53658988,
Transfer53699fc4, Resize536729ec. Create allocates workers, invokes constructors,
binds lower service pointers, calls worker vtable+8 start. Native manager create
entry5362f3c8 calls factories in order Resize at5362f52c, Transfer at5362f5d4,
Fill at5362f698 through+8, checking each return0. The static factory vtables are
53d51958,53d59700,53d56bd8. Create methods contain no guard against existing
worker pointers and overwrite those pointers. Therefore a new compositor
worker must NOT call getter+create as a speculative lazy initializer.

Safe admission contract: run after the native manager's successful create
phase, require all three relevant worker pointers nonnull and their appended
owned tags present, then enter the existing firstTransfer+54 stage gate. If
any prerequisite is absent, do not enqueue private hardware work; report
unavailable/retain existing result through the caller's normal failure route.
A ready-only pointer/tag check is not a lease against concurrent destroy.
There is no newly proven safe ad-hoc initializer from arbitrary worker phase.

Manager stop calls factory vtable+c (Resize5362f86c, Transfer5362f914,
Fill5362f9d8). Manager join calls factory+14 (Resize5362fb00,
Transfer5362fb50, Fill5362fbcc); these factory methods call536b0b94 on original
worker+8. Manager destroy invokes factory+10 (Resize5362f2b0,
Transfer5362f310, Fill5362f380). These are concrete separate phase entry points,
not proof that an independently created compositor/BackResize owner is joined
before destroy. Factory destroy still does not inspect the private stage gate.
A production caller must establish that its owning task and all gate waiters
are quiesced before native manager destroy; no such independent lease is
claimed here. Do not extend the allocation lifetime merely from menu lifetime.

## Executable checks

`.../.venv/bin/python scripts/border_recovery_public_fill.py`:8 checks pass,
4 on each independently hash-pinned ROM. Uses the actual returned installer
image and all18 patches, replaces mapped original ROM for GR3x, executes native
public Fill into real queue descriptor construction, freezes failed outer wait,
executes real FillRectIip to lower packet boundary and real OnMessage+native
notification route on separate stack, then resumes retained public frames.
Only kernel queue/event and hardware body boundaries are doubled. Distinct
constants, public halfword truncation, original GPC placement, and all three
getter-without-worker cases are asserted. No real task scheduling, native
shutdown liveness, cache synchronization, DMA idle, pixels or speed is proved.

## Nonzero canvas ROI and native strip splitting

`probe_fill_roi` added to the same executable probe traces original5365900c
into its actual lower packets and executes original53769a78 request building
to GPC/Store upload boundaries. `scripts/border_recovery_public_fill.py` now
passes14 checks across both independently pinned ROMs. Full observations are
`builds/border_recovery/public-fill-roi.json`. Format0 is used, with three
unmapped8-aligned plane tokens70000000/74000000/78000000, byte stride6336 and
allocation-row admission metadata4640. GPC constants are255/128/128.

| Target ROI (x,y,w,h) | Native packets | Store origin | Store size | Plane adjustment |
|---|---|---|---|---|
|160,160,160,4000|1|160,160|160,4000|none|
|40,100,120,180|1|40,100|120,180|none|
|0,4480,6336,160|1|0,4480|6336,160|none|
|160,160,320,4000|2|160,0 each|320,2000 each|stride*160 then stride*2160|

The ordinary bar/hole packets encode `(stride,rows,visibleW,visibleH,x,y)`
as `(6336,h,w,h,x,y)`. Lower Store config+0xa/+0xc holds x/y, +1c/+1e
holds w/h. Its linked destination info at config+50 retains stride6336 at
info+1c, w/h at info+20/+22 and EXACT original plane bases at info+24/+28/+2c.
**Do not also add x/y to plane addresses for these unsplit descriptors.**
Descriptor allocation_rows at+16 is not copied to the lower packet by this
original body; extent/readability/cache ownership remains an external bound.
These original data transfers are CPU evidence; Store upload is the explicit
boundary and physical sample writes are not claimed.

The Fill pipe splits at area>=0x100000 (compare53659100 and branch53659114).
Thus sidebar160*4000=640000 and horizontalbar6336*160=1013760 do NOT split.
The forced320*4000 case does: original5365917c..c8 shifts every plane by
stride*(originalY+processedRows), keeps x=160, resets lower y=0, and uses
slice heights2000. Lower Store confirms those fields, giving global row
intervals[160,2160) and[2160,4160), and x interval[160,480) for both. There is
no extra x displacement in planes, no gap/overlap, and no extension past the
target rectangle at this observed request-construction boundary.

However the split path executes a native assertion at53659224 (return LR
53659228), line0x1c0: it compares original width*height to
stride*(originalY+processedRows). Padded-stride/nonzero-ROI requests fail this
native tight-layout assertion despite bounded observed slices; the probe
records it explicitly and does NOT turn it into successful native acceptance.
The new planner should keep each requested rectangle area BELOW0x100000 so
its stated bars/holes avoid this path and assertion. Wider/taller rectangles
need caller-side bounded rectangle partitioning with separately validated ROIs,
not an assumption that this native split path accepts arbitrary canvas crops.

### Actual planner format1: Y plus interleaved CbCr

The same probe now also runs all four unsplit ROIs with the real planner shape:
input low descriptor byte0=1, Ybase70000000, Cbase74000000, third plane0,
stride6336/allocation rows4640. Both independently pinned ROMs pass these new
cases; executable suite now16 checks. JSON entries `format1_side_bar`,
`format1_hole`, `format1_top_bar`, `format1_bottom_bar` preserve the full values.

Original Fill's format1 branch53659288 normalizes the lower packet to
**format0/layout0**. That is the stock encoding for this path; it must not be
confused with input format0, which produced lower format0/layout1 in the earlier
three-plane checks. Lower Store destination info+6/+8 likewise contains
layout0/pixel-format0. The tests explicitly assert both native packet and Store
layout values, plus Ybase/Cbase unchanged and third plane0. GPC's three
constant slots remain Y255/Cb128/Cr128 even though only Y/C output bases are
present. This is the original request construction, not an invented two-value
color pack.

All four native Store windows match the intended ROI exactly, and all pipe/
lower assertion lists are empty. No plane base receives a manual ROI offset:
nonzero origin is represented exactly once in Store x/y. Physical interleaved
sample bytes, SPF uploads, cache coherency and hardware output still require
camera acceptance; the observations stop at original GPC/Store upload boundaries.
No component recompilation or production activation was needed for this probe.

### Small whole-preview format2 and half-height chroma contract

`test_small_format2_fill_native_spf_layout_and_half_chroma_cache_contract`
executes both fmt1 and fmt2 at160x120, stride160, cacheRows120, whole ROI0,0,
Ybase70000000/Cbase74000000/third0. Public Fill suite now18 checks across both
pinned originals. JSON adds `format1_small_preview_whole` and
`format2_small_preview_whole`, including actual native cache spans and SPF
register-writer observations. No production code or compiled component changed.

For fmt2, original Fill emits packet format0/layout2; lower Store config is
likewise format0/layout2, window(0,0,160,120), basesY/C/0 unchanged. GPC constant
slots255/128/128 remain correct. The probe now additionally clones the actual
Store descriptor/config, executes ORIGINAL SPF configuration writer53773c58
and its register helpers against RAM registers, and records:

- Layout2 in SPF control bits8..11 via53779efc.
- Frame width160/height120 at register+20.
- Byte strides160 at register+10/+14/+18.
- Ybase70000000/Cbase74000000/third0 at register+24/+28/+2c.
- No pipe, lower-construction or SPF-writer assertions.

The native allocation/cache-span convention is independently executed rather
than assumed: pre534ab1a4 loads stride+14 and cacheRows+16, multiplies at
534ab214, then for fmt2 divides chroma bytes by2 at534ab218. Its two actual
cache backend calls536bbc3c cover `(Ybase,19200)` and `(Cbase,9600)` only.
Post534ab60c does the same multiplication/division at534ab67c/680 and sends
exactly these spans to536bbcc0. The third plane is never passed. Thus original
CPU API contract treats this fmt2 interleaved C plane as160*60=9600 bytes,
versus160*120=19200 bytes for Y. The test executes both original pre/post
functions with only the final cache-manager/backend boundaries doubled. Fmt1
control case emits layout0 and19200 bytes for BOTH Y and C, as expected.

Precise evidence boundary: SPF has a common frameheight120 plus layout2; these
CPU paths do not emit a separate independent chroma-height register60. Native
CPU span arithmetic and configured packing agree on the half-sized chroma
allocation contract. Silicon interpretation of layout2 and actual DMA bus
extent/absence of overflow remain unverified physically. This is sufficient
original driver/API contract evidence for the inactive candidate, not a claim
that offline RAM-register execution proved hardware memory writes. Prepared1
still skips native pre/post; caller must perform that real whole-plane cache
ownership protocol around the preview bundle and retain both allocations.
