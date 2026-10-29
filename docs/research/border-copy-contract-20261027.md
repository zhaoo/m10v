# Border copy contract — 2026-10-27

This is an offline, hash-pinned parameter and register contract, not an enabled
camera feature. Only the analyzer, its tests and this document are added. No
production implementation, firmware build or menu changes are made.

## Inputs and reproduction

Official RTOS SHA256:

- GR III: `8a4eafcad2716e0b21e9909264e1242e534f0e39e05cba82a53546ceb4070b67`
- GR IIIx: `0f11b0d28bc67932d044c5d01bc0314844a756057c89984278c73a23449a24c6`

The analyzer rejects an unknown hash or a model/hash mismatch before execution.
It emits per-address-span hashes and its own script hash; no firmware or photo
bytes are emitted. Dependencies are Python, Unicorn and the existing
`analyze_gr3_border_iip.OriginalArm` harness.

```sh
/Users/zhaoo/Desktop/code/zhaoo/m10v/.venv/bin/python -m unittest discover -s tests -p test_border_copy_contract.py -v
/Users/zhaoo/Desktop/code/zhaoo/m10v/.venv/bin/python scripts/border_copy_contract.py --model gr3 --rtos builds/gr3-extension-validation/official-rtos.bin --output /tmp/gr3-border-copy-contract.json
/Users/zhaoo/Desktop/code/zhaoo/m10v/.venv/bin/python scripts/border_copy_contract.py --model gr3x --rtos builds/gr3-border-iip-20261027/gr3x-official-rtos.bin --output /tmp/gr3x-border-copy-contract.json
```

## Native byte-plane representation

`format=6` alone does **not** establish a uint16 image. Granulation constructs
its original source at `0x5367af34..0x5367af94` with format6, flags `0x100100`,
and byte stride loaded from the source image's halfword at `+0x14`. Its original
destination at `0x5367af98..0x5367afd8` uses format6, flags `0x100000`, and its
own byte stride. The separate SPF descriptor flags `0x100002` must not be used
as evidence that this copy route requires two bytes per pixel.

Native descriptors are **0x50 bytes**, distinct from the public image ABI.
The original constructor `0x5376bba0` and plane setter `0x5376bc08` establish:

| Native field | Source | Destination |
| --- | --- | --- |
| `+9` format | 6 | 6 |
| `+4` flag field | 1 | 0 |
| `+0x28/+0x2a` visible dimensions | 6000 × 4000 | 6000 × 4000 |
| `+0x2c` byte stride | 6000 | 6336 |
| `+0x3c` plane | source token `0x70000000` | `canvas + 160*6336 + 160` |
| `+0x4c` registration handle | assigned by original registration | assigned by original registration |

For fixture canvas `0x74000000`, the byte offset is **1,013,920**, yielding
`0x740f78a0`. Source and destination visible dimensions stay equal: expanding
the descriptor's visible width would request a different operation. Pass a null
rectangle; the target offset is the destination pointer, not a crop rectangle.
The visible inner image has no requested scaling, tone transform or CPU copy.
Hardware byte identity remains unmeasured.

## Executed original graph and registers

The probe executes original `0x53681260`, including native descriptor
registration (`0x5376bfdc`), original Loader/Store construction and linking,
and graph preparation (`0x5376cd10`). The two registered descriptors appear in
source/destination order. The graph has exactly two nodes, uploaded as unit2
(Loader) and unit31 (Store), with completion cookie `context+4`.

The original format register writer `0x53870da4..0x53871108` also executes.
Addresses in the MMIO range are mapped to **ordinary fixture RAM**, with mode2
set only to bypass handshake. No hardware register is written. For native
format handle `n`, original code writes:

| Register address | Meaning verified from original ARM |
| --- | --- |
| `0x28880300 + 64*n` | format bits8..11 = 6; bit12 = native descriptor `+4` bit0 |
| `0x28880320 + 64*n` | low15 width and bits16..29 height: `6000 | (4000<<16)` |
| `0x28880310 + 64*n` | low18 byte stride: source6000, destination6336 |
| `0x28880324 + 64*n` | full plane pointer, including target offset |

Native descriptors remain unchanged except for their registration handle.
These observations prove propagation to the original register image, not DMA
semantics, border preservation, throughput or camera completion.

The harness substitutes heap allocation/free, format handle allocation,
scheduler reservation/submission, unit upload, wait, graph release and cache
backends. Two original NEON u64 shifts in resource-bitset preparation are
stepped using their ARM-defined integer semantics because this host's Unicorn
fails on those instructions; every substituted PC is reported. This is not an
unmodified full ARM or RTOS execution. No image planes are mapped: a CPU photo
load/store would fail. Register RAM does not produce pixels.

## Wait, cache and allocation contract

Original copy calls its wait helper `0x5368a510(context, 0x400)`, then graph
release `0x5376c044`, then destination cache maintenance `0x5376bd18`, and then
the Loader/Store deleting destructors. A failed wait follows that release/cache
path as well and returns0. The probe uses explicit wait-result doubles0/1;
return1 must never be interpreted as camera completion.

Destination cache maintenance covers `stride*height` bytes **starting from the
shifted destination pointer**, not the exact visible rectangle. For the fixture
this is25,344,000 bytes. The canvas allocation6336×4320 is27,371,520 bytes,
and the full shifted cache span fits. A canvas ending exactly after visible
row4160 would be insufficient for that native cache span because left160
extends the cache endpoint. Geometry validation rejects that case. Hardware
cache-line rounding and exclusive ownership still require a real owner contract.
The generic copy does not establish fresh source-plane cache cleanliness for a
new caller. All dirty fill/source data must be synchronized through the original
owner's established API before DMA; no ad hoc JPEG hook gains that right.

The original generic function requires a real original context/graph owner,
exclusive units, live source/destination buffers, task VFP/NEON state and native
allocation/lifetime rules. It is **not callable safely merely because a JPEG
worker can see those pointers**. A release return is not proof of idle/reset;
the existing release timeout behavior remains a blocker to reuse on failure.

## Public service investigation

The original public client `0x534ab7a0` has an equal-format branch at
`0x534ab874`. An executable probe with public source/destination descriptors of
format1 records:

- factory `0x5369a0e8`;
- opcode **`0x010e8006`**;
- dispatch helper `0x534aad6c`, completion mask `0x400`;
- parameter object containing source and destination public descriptor pointers;
- service dispatch argument derived from the factory result's `+4`, plus8.

The fifth argument1 suppresses public pre/post cache handling in this probe.
The dispatcher is intercepted and does not run. This proves routing only; it
does not establish a synchronous wait, a JPEG-safe caller, cache handling with
argument0, native ownership, failure quiescence, or actual size-preserving DMA.
Do not substitute this unverified route into production.

The unequal format1→2 branch constructs `0x010e8001` (including bit15), whereas
worker `0x53658cfc` forwards its packet to `0x53768820` through worker context
`+0x44`. Worker `0x53658e68` forwards a different packet to `0x53768ec8`.
Client `0x534aba38` instead selects factory `0x5368c94c`, opcode `0x00708001`
and dispatch mask `0x80`; it must not be conflated with the equal-format route.
The supplied FillRect chain remains separate:
`0x534abc18 → 0x53658a68 → 0x5365900c → 0x53769a78`.

### Resolved same-format worker and usable public signature

Further tracing resolves this route as **TransferRectService**, using its own
hardware transfer engine rather than the borrowed generic IIP context. Its
factory vtable is `0x53d59700`. Factory initialization `0x53699fc4` constructs
workers `0x5369a2c0` and `0x5369aedc`, stored at factory `+4/+8`.
The public same-format copy goes to the first worker:

`0x534ab7a0 → 0x5369a0e8 → 0x5369abc8(opcode0x010e8006)
→ 0x5369a948 → 0x5369a40c(per plane) → 0x537e2814 → 0x537e25fc`.

The candidate API signature, derived from register/stack use, is:

```c
/* Existing original caller object required; no synthetic event/client. */
void public_copy(void *client, const void *unused_for_same_format,
                 const void *source_public_image,
                 const void *destination_public_image,
                 unsigned suppress_cache); /* original address0x534ab7a0 */
```

The first four arguments use r0..r3 and `suppress_cache` is the fifth stack
argument. Argument1 matters on other conversion branches; useNULL for this
same-format case. Use0 for original pre/post cache behavior. Do not create a
client object by guessing its event state. The routine does not expose a
reliable success result: its final operations include stack-canary bookkeeping.

The **public image ABI** used by this worker has format at0, plane pointers at
`+4/+8/+0xc`, visible width/height at `+0x10/+0x12`, byte stride at `+0x14`,
cache row count at `+0x16`, and ROI x/y at `+0x18/+0x1a`. Layout is byte`+0x1c`.
This field mapping is established by the transfer worker and cache functions;
it differs from naming assumptions in the older FillRect analyzer. In the
new worker fixture visible dimensions remain6000×4000, both ROIs are0/0,
source stride6000, destination stride6336, and destination pointers already
include the canvas offset. The worker packs source dimensions, both strides,
sourceROI and destinationROI, and the driver computes effective pointers as
`base + ROI_y*stride + ROI_x`. Do not apply the same offset twice.

Original `0x5369a948` issues luma and chroma transfers separately. Executable
probes cover format1/layout2 (both6000×4000) and format2/layout2
(luma6000×4000, chroma6000×2000). These are byte dimensions, with no color
conversion introduced. Other format/layout combinations have their own
half-width/half-height branches; do not infer them from this fixture.

The driver `0x537e2814` builds the hardware packet; it selects mode6 when
both effective pointers are16-byte aligned and mode1 otherwise. Original ARM
tests prove mode6 for margin160 and mode1 for margin68. Pointer offset68 is
valid on this service route even though the separate generic native-copy
fixture deliberately requires4-byte alignment. At `0x537e25fc`, the driver
writes transfer mode, strides, dimensions and effective plane addresses through
setters `0x537e2ef0..0x537e3004`, enables IRQ6f and starts via `0x537e2ea4`.
The traced body constructs metadata and MMIO parameters; there is no CPU photo
load/store loop. Worker tests execute original packet construction with photo
planes unmapped, intercepting the hardware start boundary. They do not produce
hardware pixels or prove DMA identity.

The public dispatch helper `0x534aad6c` enqueues via `0x536abd28`, manages its
reference-counted enqueue receipt, then waits on `client+4` for mask0x400 and
clears that event. Worker per-plane helper `0x5369a40c` clears its own
`worker+0x38` event mask0x03050001, submits through the dedicated driver, waits
using `0x536a9e8c`, clears, and calls `0x537e29e4(driver,0)` before the next
plane. The timeout comes from `0x53d5edcc` (official fixture value0xffffffff).
The worker then notifies the original client via its vtable+8 using completion
code0x03050006. This supplies an original service-owned worker/event route
without borrowing the capture task's IIP event/context.

**Failure remains unclosed.** Both original per-plane and public dispatch
helpers ignore their wait return. A failed-wait executable probe still performs
driver handoff and starts the second plane; the worker completion is not a
success predicate. `0x537e29e4` needs a proven stop/IRQ/callback quiescence
contract before buffer reuse or JPEG encode. A normal synchronous success path
is a promising integration contract, but neither JPEG caller reentrancy nor
failure safety follows just from its existence. In particular, calling it from
its own worker could deadlock. No production activation is authorized by this
research.

Original pre-cache helper `0x534ab1a4` and post-cache helper `0x534ab60c`
execute in separate fixtures. They cover Y=`stride*cache_rows`, chroma=the same
for format1 or half for format2, beginning at the plane pointers; they do not
subtract pointer offsets. For6336×4000 these spans are25,344,000 and
12,672,000 bytes respectively. This full span must fit owned allocations even
when a destination pointer is shifted. Helpers touch plane+4 and+8, so layout
or allocation differences need their own explicit contract. Cache backends are
intercepted; hardware cache effects remain untested.

## Acceptance boundary

Offline tests cover both official hashes, corrupted/model-mismatched inputs,
target offset, equal dimensions, byte strides, native flags, graph binding,
original format register propagation, failed wait and allocation/cache bounds.
No firmware is generated and no production activation is ready. Remaining
requirements are hardware byte identity, canvas fill/copy interaction, original
pool allocation, cache-line ownership, public service/JPEG ownership, safe
failure reset, capture/JPEG integration and measured camera behavior/latency.
