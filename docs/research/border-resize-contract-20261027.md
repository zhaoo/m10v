# Border preview and thumbnail resize contract — 2026-10-27

Offline research only. No firmware build, production integration or hardware
activation. The executable analyzer and tests use the same two official RTOS
hashes as `border_copy_contract.py` and reject unknown/model-mismatched images.
Every analyzed span and the analyzer itself receives a SHA256 in the JSON.

## Correct public route

`0x534aba38` is **not arbitrary resize**: its factory `0x5368c94c`, worker
`0x5368cb7c` and driver `0x537642d8` implement fixed unity affine transforms,
including width/height swapping. The public client does not read destination
width/height. This route cannot fit the expanded canvas into smaller outputs.

The actual public resize entry is:

```c
/* Original client object/event required. Address0x534ab6b8. */
void resize(void *client, const void *source_public_image,
            const void *destination_public_image, unsigned suppress_cache);
```

It uses ResizeFactory `0x53672c48`, factory `+0xc` worker, opcode
`0x00708002`, public dispatch helper `0x534aad6c` and completion mask`0x40`.
The factory creates that worker with constructor `0x53672e10`. Initialization
`0x53672be0..0x53672bf0` assigns the original ResolutionConvertService to
worker`+0x34`, and the original transfer service to worker`+0x38`.

The worker body `0x53673098` compares source/destination visible dimensions,
formats and operation mode. Unequal dimensions build a normal conversion
parameter object with source/destination pointers, unity ancillary values and
no custom color/LUT data. It calls
`0x53770bf0(ResolutionConvertService, parameters, 2)` at `0x536733e0`.
The third argument2 selects the original resolution-service completion channel;
it is not a resize scale factor. Do not substitute the other factory worker
`0x536725b8`: that belongs to another factory slot and uses a different service
completion channel.

Original public image fields are format byte0, planes`+4/+8/+0xc`, visible
width/height`+0x10/+0x12`, byte stride`+0x14`, cache row count`+0x16`,
source/destination ROI x/y`+0x18/+0x1a`, and layout byte`+0x1c`.
Use expanded visible canvas dimensions6320×4640 with actual stride6336.
The output descriptor carries its actual smaller dimensions while preserving
its allocation stride. Set both ROIs0/0 to resize the entire expanded canvas.
Do not encode the original720×480 or160×120 capacity as the visible image size
when the resized result occupies654×480 or160×116.

## Executed original ARM evidence

The probe executes public request construction, intercepts OS dispatch and then
executes the captured original worker parameters separately. It does not
simulate threads or pretend that the public queue actually ran. The full
original ResolutionConvertService request construction `0x53770bf0` and the
scaler configuration computation `0x53765a5c..0x53766910` execute. Their
computed configuration is recorded. No arithmetic stub or NEON stepping is
needed for this resize path. Hardware unit configuration uploads at
`0x53765a24` and `0x5377448c`, scheduler ownership/submission, OS event waits
and resource release remain explicit ABI test boundaries.

Photo planes are unmapped. The executed request path and scaler coefficient
computation perform no CPU image pass. The generated scaler configuration is
metadata, not an image; actual unit upload, DMA filtering, encoded output and
camera performance are untested. There are no fabricated pixels/completion
bytes. The original routine returns with no assertion in each case below for
both official GR III and GR IIIx images:

| Target | Luma request | Source chroma samples | Destination chroma samples |
| --- | --- | --- | --- |
| Preview format1/layout2 | 6320×4640 → 654×480 | 3160×4640 | 327×480 |
| Preview format2/layout2 | 6320×4640 → 654×480 | 3160×4640 | 327×240 |
| Thumbnail format1/layout2 | 6320×4640 → 160×116 | 3160×4640 | 80×116 |
| Thumbnail format2/layout2 | 6320×4640 → 160×116 | 3160×4640 | 80×58 |

The internal chroma sample widths are halved for interleaved CbCr; this does not
halve the byte stride. Source stride remains6336; output strides remain720
and160 respectively. Format1 maintains422 organization; format2 requests the
original422→420 chroma subsampling. Neither invokes a custom LUT/color transform.
Choosing format2 is still a chroma sampling change and should match the original
consumer's format. Other layouts/formats need separate proof.

These even output examples fit existing capacities. Their aspect ratios differ
slightly from6320/4640 because of integer/even rounding. This analyzer proves
request propagation, not a mathematically exact ratio or a product rounding
policy. A caller's geometry planner must choose its documented rounding rule
and encode the actual selected dimensions. No silent CPU resize is a fallback.

## Ownership, wait and failure boundaries

The public API uses its original service-owned worker and original client event,
so it need not borrow the capture task's IIP context. That is an ownership route,
not a license to construct a fake client or call it recursively from its own
worker. Serialization/reentrancy with the JPEG worker must be established from
actual original callers before integration.

The original resolution service submits and waits separately for luma and
chroma using service`+0x48`, **mask4**, timeout loaded from`0x53d5edcc`
(official fixture value`0xffffffff`). It clears the event and finally enters
release `0x5376d86c`. Public dispatch separately waits on client`+4`, mask`0x40`.
The original worker dispatcher emits its completion through the client's
vtable`+8`; that completion means the worker returned, not that all hardware
pixels were independently verified.

A failed-wait double0 still proceeds to the chroma pass and release. Wait
returns are not checked as success predicates. The shared IIP release/abort
quiescence gap applies; this route must not encode partial output, reuse buffers
or retry automatically after an unresolved wait. No failure-safe production
integration is established by these tests.

With `suppress_cache=0`, original public helpers `0x534ab1a4` and
`0x534ab60c` apply their normal pre/post cache spans, based on stride×cacheRows
and format-specific chroma size. This probe uses1 to isolate request flow;
copy-contract fixtures separately execute those original cache helpers. Preserve
full allocation/cache bounds and owned plane lifetimes through completion.

## Reproduction and remaining work

```sh
/Users/zhaoo/Desktop/code/zhaoo/m10v/.venv/bin/python -m unittest discover -s tests -p test_border_resize_contract.py -v
/Users/zhaoo/Desktop/code/zhaoo/m10v/.venv/bin/python scripts/border_resize_contract.py --model gr3 --rtos builds/gr3-extension-validation/official-rtos.bin --output /tmp/gr3-border-resize-contract.json
/Users/zhaoo/Desktop/code/zhaoo/m10v/.venv/bin/python scripts/border_resize_contract.py --model gr3x --rtos builds/gr3-border-iip-20261027/gr3x-official-rtos.bin --output /tmp/gr3x-border-resize-contract.json
```

Remaining gates: original JPEG caller/reentrancy, real scheduler ownership,
coefficient/register upload acceptance, supported extreme downsample ratios,
cache/pool allocation bounds, failure quiescence, format-matched JPEG dimensions,
actual pixels and measured camera behavior. No firmware was emitted.
