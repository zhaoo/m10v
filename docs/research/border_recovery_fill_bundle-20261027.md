# Bounded native Fill bundle prototype

Inactive compiled adapter, no camera activation or root builder/export changes.
The requested reduction is in RTOS queue/callback count; no camera latency claim.

## ABI and admission

Independent header: `native/gr3/m10v_border_fill_bundle.h`.
Entry: `m10v_border_fill_bundle_submit(private_client, immutable_bundle)` in
`m10v_border_wait_guard.c/.h`, exported by the existing opt-in research installer.

- Header: uint32 tag=`0x42464231`, count=1..132, bytes=12+12*count.
- Each 12-byte rectangle: uint32 native destination descriptor pointer;
  uint16 Y,Cb,Cr,reserved0. This is exactly the original single-Fill parameter
  shape, including the padding halfword. Header maximum allocation1596 bytes.
- Each descriptor must be a readable original native32-byte descriptor, format
  0..2, nonzero width/height/stride/canvas-height, and width+originX<=stride,
  height+originY<=canvas-height. These are strict bundle admission checks,
  not changes to normal native Fill. Descriptor controls are validated before
  any native Fill; valid readable pointers remain the caller's responsibility.
- Bundle and descriptor metadata are immutable while pending. This API does
  not provide address-space validation or protection against hostile concurrent
  writes. Count is snapshotted and range-checked before loops, never used as an
  unchecked CPU loop bound. No loop touches pixels or scales with image area.

Private client now occupies76 bytes: all prior offsets retained, bundle pointer
at68 and bundle_error at72 added. Use the header type/sizeof, not old68-byte
storage. Constructor zeros the full object. Existing client prepare clears
bundle fields; entry prepares pending before original enqueue and then binds
its bundle identity. Do not manually enqueue a header through the public Fill
without this entry; normal Fill keeps its original descriptor interpretation.

Caller prerequisites remain unchanged: successful native worker-create phase,
all owned worker allocation/constructor hooks installed before that phase,
complete-frame private stage gate held, no native factory teardown during owner
or waiter lifetime, and all pixel allocations/native descriptors retained.
The entry does not manufacture worker readiness or an allocation lease.

## One queue, many original Fill operations

Entry validates all metadata before setting pending. Invalid tag/count/bytes,
misaligned/null descriptor or invalid shape/reserved returns0 without enqueue
and without setting pending. A busy/foreign client likewise returns0.

It calls exact public534abc18(client,bundle,0,0,0,prepared1) once. That constructs
one original queue job010e0004, retaining the public stack and its common wait
until private final completion. Only an exact owned client with the bound
bundle identity gets bundle interpretation in the Fill body hook.

Within the existing active Fill worker tail, scoped body validates the bundle
again, then invokes ORIGINAL5365900c(worker,&rectangle[i]) for every bounded
rectangle. These calls construct original lower IIP packets. Original lower
53769a78 still sees its genuine5365900c caller LR536591cc or53659258; no new
parent-frame guess is used. All original inner wait and pre-release guards
remain applicable for every rectangle. On final original Fill return the scope
clears its tail, and original OnMessage emits exactly ONE03070004 notification.
Native notify534aab0c signals mask10; private pending clears after native notify
returns and inflight becomes0. Submit returns1 only then. This is CPU/lifetime
completion evidence, not a new silicon-idle guarantee.

Malformed or mismatched bundle observed after enqueue sets bundle_error1 and
enters fatal retain. It never returns to original dispatcher, emits completion,
advances rectangles, or frees buffers. Failed inner completion wait similarly
retains the current original Fill/lower frames and all earlier owners; normal
original release is unreachable while completion predicates are unsatisfied.
These indefinite failure holds do not provide bounded recovery; restart and
native shutdown coordination remain separate requirements. A normal private
Fill without bound bundle and all stock-client Fill calls keep original behavior.

## Prepared cache prerequisite

The single public call uses prepared1 exclusively. Therefore original public
pre534ab1a4/post534ab60c image/cache methods do not execute. Caller MUST perform
its real whole-canvas native cache-ownership pre/post protocol ONCE around the
bundle, retaining ownership across all rectangles and final callback. Never
pass this bundle header to those methods as if it were a native image. The
adapter itself does not implement or prove that external protocol. Unknown
cache/native reservation-acquisition/teardown contracts continue to block
production activation; reducing queue count does not resolve those contracts.

## Executable evidence and artifacts

Tests were written first and failed because the new entry did not exist.
`.../.venv/bin/python scripts/border_recovery_fill_bundle.py` passes12 checks,
6 on GR3 and6 on GR3x using independently pinned mapped original ROMs and the
actual built image plus all18 exact preimage patches. Tests cover:

- Original public-call queue descriptor, three distinct rectangles/plane tokens
  and Y/Cb/Cr values, original small Fill body/lower-packet boundary, one queue,
  exact one original dispatcher/native callback and final successful return.
- Maximum132 rectangles with one enqueue/callback; no mapped pixel addresses.
- Invalid tag/count0/count133/extent and first/last descriptor rejection before
  pending/enqueue; post-enqueue corrupt count retains without body or notify.
- Real original Fill+lower prologue/wait path error: original saved caller LR
  53659258, worker identity, active tail, unchanged paused public stack, current
  rectangle only, zero callback and no native pre-release call.
- Stock native client with the same destination header bits still takes one
  original Fill body call, with no bundle interception.

Hardware body endpoints and kernel queue/signal results are explicit doubles.
Successful full IIP execution, cache coherency, physical pixels and performance
are not simulated. The failed-inner-wait check executes original graph/request
construction but replaces upload/submit endpoints to prevent hardware access.

Existing regressions also pass:16 wait/lifetime,12 pre-release,5 stage-gate,
19 installer and8 public Fill checks. Base54160000 compiled code now6184 bytes,
SHA256 `7856b22dcfa5ad84a4772c10c65772713e190d156d5858853b9d7fff6c94f416`;
entry54160648. Both model outputs have identical code and model-specific input
identity manifests. All18 original hook addresses/expected words remain the
same; linked replacement destinations are regenerated from this build. Old
5048-byte artifacts and their addresses/hash are superseded.
