# Original cache operations and prepared=1 inheritance

The proposed successful border chain can inherit the existing native cache
handoff, without adding a whole-canvas pre/post pair, **provided** it keeps all
original StillMake/BackResize/cache calls, the existing residual bridge returns
success, all plane/cache-line ownership is exclusive, and no CPU photo access
occurs after that handoff. This is a conditional coherency contract, not camera
validation or permission to delete original maintenance. A library failure is
not an unconditional clean-buffer handoff.

## Exact operation, not a generic “flush”

| Entry | Original route / operation |
| --- | --- |
|536bbc30|Returns native cache object5536d1b4; no maintenance itself.|
|536bbc3c|Checks536b09f0; nonzero ->5383c8a8. Zero -> warning and no maintenance.|
|536bbcc0|Checks536b09f0; nonzero ->5383c8a8, zero ->5383c834.|
|536bbcac|Unconditional5383c834.|
|5383c834|mode0, invalidate.|
|5383c870|mode1, clean.|
|5383c8a8|mode2, clean+invalidate; used directly by the CPU residual bridge.|

Original536b09f0 calls53050eb8 with task/context arguments and returns0 exactly
for resultffee0000. The probe supplies that OS result explicitly; it does not
execute a real task scheduler. Do not assume the result is always nonzero in
every context. A stage that requires this cache route should preserve the
original worker context and can validate the current eligibility result.

The backend5383c728 saves/restores CSSELR and calls the original critical-section
entry/exit. Its by-MVA helpers align the address down64 bytes and include the
initial offset in length. The original low-level loops issue:

| Operation | Range loop | CP15 request | Completion barrier |
| --- | --- | --- | --- |
|invalidate|530008d8|MCR p15,0,address,c7,c6,1|DSB SY at530008fc|
|clean|53000904|MCR p15,0,address,c7,c10,1|DSB SY at53000928|
|clean+invalidate|53000930|MCR p15,0,address,c7,c14,1|DSB SY at53000954|

The probe records the original CP15 maintenance requests and substitutes a tiny
explicit cache-geometry fixture for CLIDR/CCSIDR. It does not execute physical
cache effects. A range beginning60000025 with length128 issues three by-MVA
operations at60000000,60000040,60000080 followed by DSB. The selector is not a
target cache-level field for by-MVA requests; the JSON uses level=null there.

## Large clean/clean+invalidate does not walk the full image address range

For mode1/2 only,5383c6c0 compares the requested length against global55039904.
Its pinned ROM data initialization is40000 hex =262144 bytes. At/above that
threshold it invokes5383c4e8 rather than the by-MVA address loop.

That whole-cache route clears three acknowledgement words at55384700/04/08,
publishes mode at+0c, executes DSB, sends SGIs to the other two cores and waits
for their acknowledgements. It maintains local L1 using set/way. Afterward the
dispatcher separately maintains L2 using set/way. For clean+invalidate the
original L1 function53000b18 uses CSSELR0 and MCR c7,c14,2; L2 function53000cbc
uses CSSELR2 and the same set/way opcode. Both have DSB completion barriers.
Mode0/1 use c7,c6,2 / c7,c10,2 respectively.

The real remote handler5383c8e4 runs its selected L1 maintenance, stores1 to its
own acknowledgement slot, then executes DSB. The tests execute that handler
separately for cores0/1 and verify the maintenance's DSB precedes the ACK store,
followed by the handler's DSB. The coordinating core's remote ACKs are explicit
doubles; no cross-core completion or physical cache cleanliness is fabricated.

Thus the default eligible72.192MB bank call has work proportional to maintained
cache capacity, with cross-core synchronization, rather than1,128,000 by-MVA
operations. Repeating such a call still repeats costly whole-cache maintenance;
there is no offline millisecond claim. Actual set/way counts depend on physical
cache geometry, not the probe's two-set/two-way fixture.

There are two exceptions to the performance inference:

* mode0 invalidate directly uses the by-MVA loop even for a large span;
* original debug CLI can disable the address-limit shortcut. Wrapper536bbcbc
  ->5383c9a8 storesffffffff to55039900/04;536bbcb8 ->5383c93c restores4000/40000.
  Static callers5304373c/790 use ROM commands `cache flush/clean/limit` and
  “Cache Enable/Disable addr limit size”. Tests execute both controls and show
  a262144-byte mode2 operation becomes4096 by-MVA operations when disabled.

Do not overwrite that global configuration as part of border processing. Read
and report it if claiming the fast route for a particular live capture.

## Original capture handoff

After all three StillMake iterations,53502568 obtains the native cache object;
5350256c/70 reads config+10/+14 (bank5 base/capacity) and53502574 calls536bbcc0.
The executed fixture requests exactly60000000,72192000. In eligible context it
therefore performs clean+invalidate through the default whole-cache route.
The whole bank includes reserved padding, not merely the old visible image.

BackResize cleanup534ff1b8 also calls536bbcc0. The ordinary fixture retaining
the new6336 source pitch and a6000x2248 native crop produces four calls:

| Address fixture | Span | Source of length |
| --- | ---: | --- |
|72000000|57600|3*160*120 thumbnail scratch|
|73000000|76032000|3*6336*4000 RGB scratch; separate native workspace token|
|60180000|14243328|6336*2248 main Y|
|64180000|14243328|6336*2248 main C|

The public image cleanup helper534ff148 uses descriptor visible height+12 and
stride+14; it does not use cacheRows+16. Scratch cleanup separately uses its own
native rows. The fixture's unmapped scratch tokens do not prove allocation
capacity. In eligible context all four operations are clean+invalidate; the
three large calls each take the whole-cache route. Additional original branches
can clean a second descriptor. None are removed by this research.

## Existing residual bridge exits

Current source identities are SHA-pinned in the CLI JSON for
`m10v_library_capture.c`, `m10v_library.c` and `m10v_anime.h`. This audit is of
the current source, distinct from the pinned original ROM cache implementation.

| Bridge branch | CPU photo access | Existing cache handoff |
| --- | --- | --- |
|validation/allocation/custom-record rejection before rendering|None in the bridge before main render|No post clean needed for pixels not touched.|
|cpu_stages=0|None; returns before cache and render|Inherits upstream native state.|
|main render returns0|May modify Y/C|Both planes get5383c8a8 before and after, length `(H-1)*stride+W`.|
|main render returns nonzero|No unconditional bridge guarantee about partial modifications|Post5383c8a8 is conditional on result0; do not infer a clean handoff.|
|format1 independent thumbnail|May modify Y/C|Both planes pre/post5383c8a8; post is unconditional after thumb_render.|
|format2 stripe thumbnail|May modify Y and copied-back C|Both planes pre/post5383c8a8, including the loop's failed thumb_render branch.|
|format2 anime thumbnail|May modify Y/C on success|Pre clean/invalidate; post only on return0. The current inline anime function rejects during preflight before its first pixel write.|
|invalid/aliased/unsafe secondary thumbnail|Skipped|No secondary writes to hand off.|

Main rendering has late error returns around legacy color and anime after
earlier stages can have run. Valid immutable inputs may exclude these errors,
but the bridge's result type alone does not encode “no pixels changed on any
failure”. This research does not strengthen that API. Continuing to hardware
after an arbitrary negative result requires a separate clean/invalidate handoff
or a stronger proven renderer failure contract. A retained fatal owner that
never republishes those buffers is a different failure policy.

For a successful CPU pass, main clean/invalidate plus each independently
modified secondary's clean/invalidate already returns the modified cache lines
to hardware. Large main spans usually trigger whole-cache maintenance, so adding
another two60MB canvas calls is redundant under the stated ownership/no-CPU-
access conditions. Do not remove the bridge's own pre/post calls.

## prepared=1 is a caller responsibility

The actual original caller534ccba4 sets r3=1 and534ccba8 calls wrapper534c8d64.
That wrapper passes it as the sixth argument to public FillRect534abc18.
Public534abc54 skips pre method534ab1a4 when prepared is nonzero, and534abcb4
skips post method534ab60c. The executable probe runs the original callsite,
wrapper and public branches up to the dispatcher boundary. It observes only
dispatch for prepared1; prepared0 observes pre -> dispatch -> post.
The same original sequence later calls public Resize534ab6b8 with prepared1 at
534ccc20/28. These are API usage precedents, **not ownership proof for the new
canvas**.

For the new chain, inherited ownership requires all of the following together:
original completion guards have resolved; all padding/plane cache lines were
included in the unchanged native bank handoff or subsequent successful bridge
handoff; all CPU writers have completed and cleaned; metadata/header/control
writes do not alias photo cache lines; all photo owners remain exclusive; and
the following Fill/Resize path performs hardware operations without CPU pixel
access. Keep all original hardware-service internal maintenance and barriers.
This study authorizes no removal of those internal calls. The bundle header
must never be passed to native image/cache methods as if it were a descriptor.

## Verification and remaining evidence

```sh
/Users/zhaoo/Desktop/code/zhaoo/m10v/.venv/bin/python -m unittest discover -s tests -p test_border_cache_contract.py -v
/Users/zhaoo/Desktop/code/zhaoo/m10v/.venv/bin/python scripts/border_cache_contract.py --model gr3x --rtos builds/gr3-border-iip-20261027/gr3x-official-rtos.bin --output /tmp/gr3x-border-cache-contract.json
```

Six cache tests pass on both pinned ROMs. The JSON records ROM/analyzer/span
hashes, original instruction requests, fixture geometry and remote ACK limits.
`tests.test_gr3_border_early_library` also passes the current ten-slot producer
->early Setup6->native-only bridge path with unmapped photo planes and forbidden
pixel/cache/allocation access.

An extra run of three older capture tests failed before reaching their cache
logic: `test_gr3_m10v_library_arm.py:81` accepts state lengths104/64/44 but the
current runtime writes184. The affected methods are native-only all-films,
independent playback thumbnails, and unsupported-tone/RAW/CFA rejection, totaling
48 failures including46 film subcases. Those stale fixtures were not edited,
and their attempted run is not counted as successful cache evidence.

No physical cache behavior, cross-core latency, DMA pixels or camera performance
is claimed. No production source/build/cache setting was changed for this study.
