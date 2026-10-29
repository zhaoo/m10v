# BackResize, early Setup6, and stripe offsets

Offline original-ARM evidence for official GR III and GR IIIx RTOS images;
the scripts reject other hashes. No firmware activation or camera result is
claimed. Photo planes remain unmapped. OS submit/wait/cache operations are
explicit doubles; these tests prove metadata propagation, not DMA completion.

Run:

```sh
/Users/zhaoo/Desktop/code/zhaoo/m10v/.venv/bin/python -m unittest discover -s tests -p test_border_backresize_contract.py -v
/Users/zhaoo/Desktop/code/zhaoo/m10v/.venv/bin/python scripts/border_backresize_contract.py --model gr3 --rtos builds/gr3-extension-validation/official-rtos.bin --output /tmp/gr3-border-backresize-contract.json
```

Four tests pass on both pinned ROMs. The JSON includes the complete ROM digest,
analyzer digest, and exact original instruction-span digests.

## Three StillMake stripes: retain the byte offset

The original geometry builder `53660558` writes status halfwords
`+102/+104/+106` to `[0,1960,3944]` at `53660c74/53660ca8/53660cb8`.
The status copy loop `5365e5e0..5365e600` preserves those halfwords, ultimately
at recipe `R2aa/R2ac/R2ae` because the status base is `R1a8`.

StillMake reads one halfword at `53501f00`, then `53501f14/18` adds it directly
to config `C+18/C+1c` and stores module `+9950/+9954`. There is no multiply by
the original pitch or row count. The executed writer -> copy -> three output
binding fragments produce `Ybase+[0,1960,3944]` and `Cbase+[0,1960,3944]`.
Changing R2Y output pitch therefore needs **no conversion of this offset**.
It represents a horizontal byte-column displacement for the original format1
Y/interleaved-chroma output, with Y and C receiving the same displacement.

The test seeds the writer fragment's register inputs and does not execute the
camera's property initialization selector. It does not prove that every
alternate capture mode retains this array. A runtime adapter must validate the
actual three offsets and each stripe width against the original row pitch
and new reserved row/plane capacity before publishing each R2Y request. Native
halo widths can extend12 bytes beyond visible width; the implemented admission
and original register evidence are in `border-prepare-contract-20261027.md`.
Reject an unsupported
array; do not reinterpret it as rows. Common RAW/status pitch remains unchanged.

## BackResize uses the low source descriptor pitch

`534ff294` consumes config `+3c=R70 source`, `+40=Rb0 main`, followed by the
small-preview descriptors. `534fec98` copies the source low descriptor into
module scratch `+8a48`. Native crop setup computes centered offsets from source
visible width/height and settings `+b38/+b3a`. At `534fed08` it reads the scratch
descriptor's stride `+14`, then adds `x+y*stride` to both Y and C planes.
Common recipe `R252` is not read for this crop displacement.

Actual `534ff294` execution with stride6336 yields:

| Desired crop fixture | Native plane displacement | Visible result |
| --- | ---: | --- |
| full | 0 | 6000x4000 |
| XPan geometry | 876*6336 | 6000x2248 |
| 6x7 geometry | 668 | 4664x4000 |

These names describe geometry fixtures: the dimension-property query is doubled,
not an execution of the camera menu's actual aspect-selection logic.

The original ordinary mode aliases main Y/C to the cropped source pointers
(`534fee18/20`), and copies the crop descriptor back to R70 (`534ff494`). Thus
the initial source/main difference of144 rows is required before this stage,
but intentionally disappears at this stock stage. Do not collapse it earlier.
Main stride is not rewritten by these pointer stores: both R70 and Rb0 must
already carry the same validated new pitch. Keep visible source/main geometry
native until BackResize finishes, because native property-derived dimensions
would otherwise recrop an expanded canvas.

The test also executes nonzero low ROI `(12,8)`: source/scratch preserve it,
while main retains its own zero ROI. The crop arithmetic does not normalize it.
The minimal supported adapter should require zero native low ROI unless the
combined displacement and both descriptors' semantics have been separately
proved. Final source size cannot reconstruct the original full-source plan
after this mutation; retain the frozen plan or use unchanged common source
dimensions plus validated bank identity and native crop pointers.

Native `cacheRows+16` remains4000 after an XPan visible-height crop2248. A later
generic cache operation using `stride*cacheRows` from the cropped plane can
overshoot the reserved canvas. BackResize's own cleanup uses visible height,
but a compositor must establish bounded rows before invoking later generic
library/cache clients; validate every plane's actual cache extent.

## Native worker route and CPU boundary

BackResize gets ResizeFactory `53672c48` slot `+8` at `534fe7dc/e0`, stores its
worker at module `+8a0c`, and submits opcode `00708001`. Handler `53671ab0`
dispatches this to `53671224`. Its original helper `53670f88` forwards source
and destination low-descriptor pointers to ResolutionConvert `53770bf0` when
dimensions/format differ (`53671038`). The service's real low-descriptor pitch
and scaling propagation are separately covered by `border_resize_contract.py`.
The filter/preview coordinator can additionally call `537672ac`; no claim is
made that every branch of that large filter path has been executed here.

There is an existing CPU pixel-fill branch, unrelated to the proposed border:
when the thumbnail descriptor has nonzero ROI, `536712c8` fills Y with zero and
`536712e8` fills C with8080 over stride*rows. Consequently these tests do not
prove that the whole stock BackResize worker is always free of CPU pixel work.
A strict no-CPU scope must reject that branch and require zero thumbnail ROI.

## Early Setup6 is metadata-only in the executed scope

Recipe dispatch `5350e624(recipe,6)` selects `5350ea50..5350eabc`. It copies
R70 semantic descriptor fields into R110 through original `536a3d84`, then
writes the fixed JPEG context pointers below. No allocator or work-publish call
is reached; the fixture rejects the watched native allocation/queue entries.
Repeating Setup6 with unchanged source produces identical JPEG context fields.
Stage5 setup leaves the JPEG context untouched.

| R9b8 context offset | Recipe target |
| --- | --- |
| +30 | R1a8 status |
| +34 | settings pointer from R44c8 |
| +38 | flags pointer from R5c |
| +3c/+40/+44 | Rb0/Rd0/Rf0 |
| +48/+4c | R110/R130 |
| +50/+54/+58 | R148/R160/R178 |

This makes direction A the smaller adapter contract: at `534ff458`, after the
original cleanup (`534ff454`) but before the BackResize worker's owner callback,
call the real Setup6 to construct the full existing JPEG context; run the
existing capture library once; then compose/publish the framed descriptors.
The earlier `534ff450` boundary precedes cleanup and is unsuitable for new pixel
writes that cleanup might invalidate. The native submission/wait body is called
at `534ff44c`; its wait ignores failure, so a valid completion guard remains a
separate prerequisite. A zero test-double wait still reaches four cleanup cache
calls in the offline probe.

The integration must establish exclusive current-recipe ownership while the
master is waiting for this stage's callback. These probes do not execute the
scheduler or prove that ownership globally. The later normal Setup6 will copy
R70 into R110 again: both descriptors must describe the same intended framed
image at that point, or the adapter must repair R110 at the proven boundary.
Existing library work needs a per-recipe/frame deduplication marker so the later
JPEG hook does not apply halo/stamp/style twice. Its own recipe/snapshot/cache/
ISP-mask preconditions still apply; Setup6 being metadata-only does not waive
them. A late JPEG-only composition remains insufficient because first Review
has already copied the old descriptor.

Runtime remains inactive. Hardware completion, recovery retention, filter-path
coverage, strict branch gates, library deduplication, and first-Review/JPEG
descriptor consistency must be integrated and validated by their owners.
