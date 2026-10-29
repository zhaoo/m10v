# GR III original IIP cancellation and failure quarantine contract

Status: **nine new original-ARM CPU-control-flow checks pass; failure recovery remains blocked.** No camera activation, MMIO experiment, silicon/DMA model, native source change, package, or commit is part of this research.

## Fixed input and reproduction

GR III 2.10 RTOS: `builds/gr3-extension-validation/official-rtos.bin`, SHA256 `8a4eafcad2716e0b21e9909264e1242e534f0e39e05cba82a53546ceb4070b67`.

```sh
/Users/zhaoo/Desktop/code/zhaoo/m10v/.venv/bin/python scripts/border_recovery_contract.py
/Users/zhaoo/Desktop/code/zhaoo/m10v/.venv/bin/python scripts/border_recovery_contract.py --disassemble
```

The second command prints exact instruction bytes, addresses and range hashes. A local copy is `builds/border_recovery/original-control-flow.txt`. The nine tests run original code RX, with register images mapped to ordinary RAM. Only named logging/synchronization/callback/top-clock endpoints are replaced; tests do not generate pixels or status changes. The input is GR III; no GR IIIx whole-image or per-range equality check was added by this script.

## Owner cancellation is now traced through its original service

The original `ResolutionConvertService` vtable holds `0x5377096c` at `0x54034fd4`; its secondary base thunk at `0x54035000` is `0x537709b0`, which adjusts `this -= 8` and branches to that routine. RTTI/name strings in this table region identify `24ResolutionConvertService`; source diagnostic strings identify `Basic/src/ResolutionConvertService.cpp`.

| Original address | CPU action |
| --- | --- |
| `0x5377096c..0x5377099c` | Emits one diagnostic through `0x536b82d4`. |
| `0x537709a0..0x537709ac` | Loads `ResolutionConvertService + 0x38`, restores frame, tail-calls `0x5376daf0`. |
| `0x5376daf0..0x5376daf8` | Loads `IipService + 0x24`, sets `r1=1`, tail-calls `0x5377876c`. |
| `0x5377876c..0x537787a4` | For nonzero flag, loads driver `+0x14`, reads register `+8`, clears low two bits, writes it, returns. |

`0x540356c8` contains `AbortMultipleImageProcess`, referenced by the driver's assertion branch when flag is zero. The actual original cancellation chain always passes flag one. For all eight possible low-three-bit status combinations, the full chain executes and leaves register `+4` unchanged, changes control `+8` from `0xa5a50003` to `0xa5a50000`, and calls only the logger. It neither calls the status predicates nor waits/clears an event. **This is an owner cancellation request, not a completion/idle acknowledgment.** Its name must not become an integration safety assertion.

An aligned whole-image direct-branch scan found the service forwarding branch `0x5376daf8` to the driver, and original owner forwarding `0x537709ac` to the service. This is a locator, not a proof that indirect or other architectures have no additional callers.

## Interrupt dispatch preserves owner routing; AXI error does not reset

`IipService` installs IRQ callbacks for IDs `0x5a/0x5b/0x5c` in initialization at `0x5376ce74..0x5376cecc`; vtable entry `0x54034ddc` points to dispatcher `0x5376d0e8`.

The dispatcher reads current ownership masks at service `+0x100`, `+0x104`, and `+0x108`, then forwards a message through `0x535628dc` using the corresponding callback object at service `+0x3c`, `+0x58`, or `+0x74`. For ID `0x5a`, bit zero maps to message `0x02150001`. The original control path at `0x5376d124..0x5376d14c` chooses the first matching mask; `0x5376d4fc..0x5376d510` implements the first-owner forwarding arm. Tests execute all three arms and verify original mask fields remain intact.

For ID `0x5a`, bit two (`r2=4`), `0x5376d150..0x5376d194` calls register readers `0x5377949c` and `0x537794ac`, emits `[IIPS] InterruptParamIip_Axi_Error %x %x` through logger `0x536b82d4`, and returns zero. With no completion bit set, this original error path calls no owner callback, abort, reset, or event wait. Test leaves busy status and low control bits unchanged. The IRQ driver's hardware pending-bit acknowledgment, if any, is outside this dispatcher test; acknowledgment alone would also not establish DMA drain.

**Implication:** replacing a graph/owner mask after failure risks late events being associated with the next owner. Neither an empty local event nor a newly allocated image buffer closes this shared-service race. The extent to which hardware can emit late events remains unmeasured; software routing is proven.

## Initialization and macro gating are not a proven reset protocol

The service virtual lifecycle slot at `0x54034dd4` points to `0x5376cffc`. That function calls top-clock service `0x5377c4d4(top, 0xf, 1)`, initializes IIP control fields through native setters, calls `0x5377c4d4(top, 0xf, 0)`, selects clock code zero via `0x5377d780`, and returns **constant one** at `0x5376d0e0`. It does not call either release status predicate, does not wait for an event, and does not invoke AbortMultipleImageProcess. The executable test runs all IIP native setters and explicitly replaces only the two top-clock endpoints; busy status low bits and control `+8` remain unchanged.

This is evidence against treating a successful virtual lifecycle initialization return as recovery acknowledgment. It does not establish what an actual clock transition does to silicon. The underlying `0x5377c4d4` dispatches into ImageClockDriver setters `0x5377f548/5a4/600/65c`, which read-modify-write packed two-bit fields at fixed MMIO `0x1d021000+0x5c`; those setter bodies contain synchronization plus one field write, no IIP status/IRQ poll. They are not a demonstrated DMA reset/drain handshake.

Macro access helper `0x5376eb2c(service, enabled)` uses lock `service+0xb8` and reference count `service+0x10c`. A disable request decrements the count; only transition to zero calls top-clock `0x5377c4d4`. The original release calls this helper after its idle loops. The added test proves a disable with count two leaves count one and calls no top backend at all; disable to zero calls the backend but still does not inspect idle. Therefore calling this helper, setting the count to zero, or observing the clock write cannot authorize freeing active DMA memory. **Do not force shared counts or run service initialization while other owners exist.**

## What the existing release contract actually accepts

Driver predicates:

- `0x53778490`: `((status_at_driver_registers_plus_4 >> 2) & 1) ^ 1`.
- `0x53778474`: `(status_at_driver_registers_plus_4 & 3) == 3`.

Release `0x5376ed74` first waits for predicate one to become false, writes low-two status/control bits zero through `0x53778458`, then waits for predicate two to become false. Normal observed register conditions are thus bit two set before the first transition, and low-two bits not both set after the write. These names/conditions do not independently prove all bus masters drained. The loops are bounded; timeout branches `0x5376f13c` and `0x5376f118` log assertion lines `0x348/0x354` and branch back into cleanup. Existing `tests/test_gr3_iip_graph.py` executes both busy timeout paths and proves graph bookkeeping can clear while status still reports busy. A post-return check is too late to preserve owner bookkeeping that this routine has already released.

## Integration decisions

| State/evidence | Allowed continuation |
| --- | --- |
| Admission fails before submit and original ownership was never changed | Return the unchanged original image path; release only locally allocated unsubmitted workspace. |
| Submitted graph completes through its original task-bound completion path, with required completion mask and no error, and release executes its ordinary non-timeout path | This is the original firmware's normal software completion contract. It supports further offline integration work, but silicon/memory/performance acceptance is still required before border activation. |
| Wait timeout/error, missing completion bits, late/unmatched event, failed idle predicate, release assertion, or uncertainty whether submit took effect | Quarantine all new DMA-visible buffers/graph workspace and prevent new requests on the affected **shared IIP service**; preserving only the border buffer does not make later photos safe. Do not CPU-fallback on partial output, retry, free/reuse, replace owner masks, or blindly reset clocks. |
| Only high-level FillRectIip returned, cancel returned, release cleared bookkeeping, lifecycle init returned one, macro reference count became zero, or a clock field was written | Insufficient to leave quarantine. |

The existing FillRectIip helper ignores event-wait status and invokes this release. Consequently its return does not tell an adapter whether the ordinary release path or the timeout/log-and-continue path ran. A new safe adapter cannot simply wrap that function and inspect its return.

**No implementation-ready native recovery address/protocol has been proven.** Concrete original owner addresses and control flow above narrow the remaining work: identify a hardware-specific stop/reset acknowledgment plus IRQ drain/rearm sequence owned by the shared service; preserve exclusive scheduler ownership and all DMA-visible lifetimes until acknowledgment; prove failure is propagated before native release drops ownership. A persistent poison flag is useful for blocking subsequent plugin operations, but it cannot prevent the unmodified original camera scheduler from using the same IIP service. Until the owner-level refusal/recovery path is established, keep border hardware activation blocked. This is a bounded research conclusion about inspected paths, not a claim that no recovery mechanism exists anywhere in firmware.

## Exact idle observations, lock scopes, and the viable pre-release boundary

This refinement separates native software acceptance from abort and from timeout recovery.

(a) **Driver-defined ordinary idle acceptance:** before the first transition require `0x53778490(driver) == 0`, equivalently `(status & 4) != 0`. Then original `0x53778458(driver, 0)` performs a read-modify-write of low two bits at status/control register `+4`; require `0x53778474(driver) == 0`, equivalently `(status & 3) != 3`, on the subsequent observation. First-status low3 values 4/5/6/7 pass the first predicate; subsequent low3 values 4/5/6 pass both boolean conditions. The second original loop itself does not recheck bit two. Requiring both conditions remain true over subsequent observations would be an additional conservative guard, not a stock proven stable-drain protocol. The sixth test runs the complete original release with actual getter/setter bodies, changes only ordinary RAM status at the second loop observation, and proves normal first4/5/6/7 -> second4/5/6 paths have no timeout assertion. First0 asserts348; second7 asserts354; both still enter original cleanup.

(b) **Abort:** `0x5376daf0(service)` forwards the real command to its real driver. It can be issued while retaining ownership, but its return adds no acknowledgment. It does not establish either condition in (a).

(c) **Timeout:** no guaranteed drain/reset contract is established. A failure-only owner retention path may wait for later *observed native conditions*, but must not be represented as a performance solution or as a bounded successful recovery. A deadline may expose a fatal error while ownership remains retained; it cannot authorize freeing memory or advancing the recipe. Without a gate over every shared owner, even this fatal hold is not currently proven safe.

Concrete roots:

- Existing graph-owned API: `graph_owner = *(context+8)`, `IipService = *(graph_owner+4)`; pointers alone do not confer ownership.
- Original FillRectIip: `FillContext = *(FrameOperationPipeService+0x44)`, `IipService = *(FillContext+0xc)`. Do not apply the graph API root formula to FillContext.
- Both reach `driver = *(IipService+0x24)`, `registers = *(driver+0x14)`. Official factory instructions `0x537797a8..0x537797c8` assign register base `0x28880000` and data aperture `0x29820000`; status/control is `0x28880004`, abort control is `0x28880008`. Read the driver's root under original ownership instead of treating raw MMIO addresses as an independently safe API.

The original locks do **not** yet establish exclusive failure retention:

| Scope | Exact original path | Proven limit |
| --- | --- | --- |
| Frame pipe mutex `FrameOperationPipeService+0x34` | `0x53659108..0x53659118` or `0x53659248` requests acquire with timeout5000 through `0x536a848c`; `0x53659228..0x5365922c` releases via `0x536a8544` | Serializes this pipe when acquire actually succeeds; acquire return is not checked by this caller. No evidence all other IIP clients use this mutex. |
| IipService reserve/release lock `+0x90`, mutex `+0x14` | Reserve `0x5376ec8c..0x5376ecb0`, release `0x5376ee5c..0x5376ee88`; release unlocks `0x5376ef98..0x5376efac` | Does not cover the full submitted-job/event-wait lifetime or every submission entry. |
| IipService submission lock `+0xa4` | `0x5376e5b4..0x5376e5cc` acquires; `0x5376e7c8..0x5376e7d4` unlocks before caller waits | Submission writes owner mask `+0x100/+0x104/+0x108` **before acquiring this lock**, at `0x5376e858/0x5376e864/0x5376e7d8`. Holding this lock cannot by itself prevent a competing caller from replacing the IRQ routing mask before it blocks. |

The seventh test executes each of the three submit branches and stops **at entry to the shared-lock acquisition**, before the synchronization backend can return. In all three cases its selected ownership mask has already become `0x1234`. This is a concrete CPU counterexample to the proposed claim that retaining `service+0xa4` **alone**, with no reservation ownership, excludes owner reuse. It does not show that another legally reserved same-category caller can bypass the native category semaphore. It does not require real concurrent threads or simulated hardware.

For FillRectIip, a precise hook candidate is **`0x5376a374` immediately after event wait**, before original event clear. At this boundary wait result is still r0, `r6=FillContext`, event output lives through `sl`, `sb` is event object, `r8` is request mask. Graph release arguments are reconstructed by `0x5376a380..0x5376a38c`: r0=`*(r6+0xc)`, r1=`*(fp-0x2d0)`, r2=`fp-0xb0`. Hooking at `0x5376a380` is later: the event was already cleared at `0x5376a37c`, so wait result has been clobbered unless saved earlier. The large original stack frame remains live before release. Retaining the worker at this boundary would retain its stack graph and outer pipe scope, unlike returning from the helper and retaining only image planes.

However, the pre-release boundary alone does not prove the other shared clients are excluded. An implementation-ready fatal-hold design needs exclusion **before every competing reservation/submission can alter this owner**, with verified lock acquisition and coverage of competing service entry paths, then retains source/destination/workspace/callback objects and worker stack until native observations are accepted. The native reservation mechanism below is a possible way to provide this exclusion; a new broad global gate is not automatically required. An idle observation after cancellation is still distinct from draining already-dispatched callback messages; dispatcher reads current masks and callback forwarding can race changes unless owner identity remains fixed. No safe candidate should silently equate these unresolved lifetimes with a timeout message plus a plugin-local poison bit.

## Factory alias and retained reservation: a stronger, bounded route

The objects are not assumed shared merely because both have the class name IipService. Original factory wiring identifies the actual alias:

1. `0x537700a0` returns singleton factory address `0x5536f568` (guard at `0x5536f5b0`). The eighth test executes its initialized original branch and checks this literal return.
2. Factory construction `0x5376fcf4..0x5376fd14` allocates one `0x110`-byte IipService, constructs it with `0x5376d75c`, and stores it in factory `+4`.
3. Factory `+0x3c` is FillContext: allocation/construct/store at `0x5376feac..0x5376fecc`; `0x5376fef4..0x5376fefc` assigns FillContext `+0xc = factory+4`.
4. Frame pipe factory `0x53658988` calls the singleton at `0x5365899c`, loads its `+0x3c` at `0x536589a0`, and stores that exact pointer into FrameOperationPipeService `+0x44` at `0x53658a30..0x53658a38`.
5. Factory `+0x2c` is the graph-owner object: allocate/construct/store at `0x53770030..0x53770050`, then `0x53770084..0x53770090` assigns graph-owner `+4 = factory+4`.
6. The eighth test executes the actual three pointer-wiring slices with synthetic factory objects and confirms both routes reach the same supplied service. It does not execute the full allocating factory.
7. IRQ manager comes from `*(0x537887a0()+4)` at `0x5376f9e8..0x5376f9ec`; factory stores that into the shared service `+0x28` at `0x5376fd2c..0x5376fd34`. Service initialization registers its own callback for all three interrupt IDs through this manager.

The original reservation protocol means the submit-lock counterexample must **not** be overextended:

- `0x5376ebd0` acquires capacity semaphore service `+0xcc` (once or twice depending on flag), then a category semaphore `+0xd8/+0xe4/+0xf0`, then service `+0x90` and mutex `+0x14`; it increments active reservation count byte `+0xfc` under the latter locks. Semaphore timeout `*(0x53d5f11c)` and global-lock timeout `*(0x53d5f020)` both equal `0xffffffff`.
- The ninth test executes original category-zero reservation to the global-lock acquisition boundary, with semaphore/callback backends explicit doubles. Capacity and category semaphore calls occur first, all use timeout `0xffffffff`, and service `+0xfc` plus all three owner masks remain unchanged at entry to lock `+0x90`.
- Original release posts category semaphore and clears its owner mask **before** its idle loops. A pre-release hook retains that semaphore; a legal same-category caller must first obtain it before submission, so it cannot simply overwrite the same owner mask while the previous reservation remains held. Other categories have distinct owner-mask fields.
- Shared engine AbortMultipleImageProcess is not category-specific. If count `+0xfc > 1`, aborting may affect another active reserved job. A candidate must not use a global abort based only on possession of one category semaphore.

A **conditional failure-only retention protocol** is therefore concrete enough for further original-ARM verification:

1. Intercept Fill at `0x5376a374`, preserving wait result/event bits, original worker stack, context, all planes/workspace, and the still-live category/capacity reservation. Do not call original release on failure.
2. Actually acquire and verify original service `+0x90` and mutex `+0x14`, respecting original ordering. With both held, inspect count `+0xfc`. Require exactly one active reservation before issuing a shared abort. This gate blocks new native reservations before their active-count increment; the retained category semaphore prevents this owner's reuse. Existing other active reservations must be handled by their owners, not silently canceled.
3. Issue original abort through `0x5376daf0(service)` only under that sole-reservation condition. Poll the original getter-defined conditions in section (a); retain all ownership on busy. A UI deadline may mark fatal/restart-required, but cannot release memory or return to the recipe while busy.
4. Before resuming original cleanup, prove IRQ pending/forwarded callback drainage and the handoff/reentrancy rules for retained locks. Do not simply recurse into original release while locks are held without verifying lock recursion behavior; do not unlock and assume exclusion remains. The current tests do not establish those last two requirements.

The static direct-branch locator found submit call sites `0x537648d0, 0x53767874, 0x53767f68, 0x53768df4, 0x537698ec, 0x5376a354, 0x5376c6f4, 0x537715e8, 0x53771924, 0x537725b0`; corresponding operation bodies have reserve calls in the same region, including Fill reserve `0x53769cdc`, graph reserve `0x5376c4b0/0x5376c998`. This is useful evidence for auditing legal entry paths, not a completed all-caller/control-flow dominance proof.

Thus **retaining the complete original reservation plus global lock/count gate may be viable**. The stronger evidence avoids inventing global sharing and avoids demanding a new gate unnecessarily. It still does not yet authorize a hardware-active test candidate: lock handoff and interrupt drainage are explicit remaining proof obligations, alongside pixel, memory, and normal performance acceptance.
