# Private IIP pre-release observations and complete-frame serialization

Status: isolated guard implementation, twelve pre-release checks and five stage-gate checks pass. No central builder integration, camera activation or firmware output. These are **native driver-defined ordinary completion conditions**, not abort acknowledgment or formal proof of silicon/DMA bus drain.

Code: `native/gr3/m10v_border_wait_guard.c/.h`, assembly adapters in `scripts/border_recovery_wait_guard.S`; machine-readable admission requirements in `scripts/border_recovery_wait_guard_contract.json`.

```sh
/Users/zhaoo/Desktop/code/zhaoo/m10v/.venv/bin/python scripts/border_recovery_release_gate.py
/Users/zhaoo/Desktop/code/zhaoo/m10v/.venv/bin/python scripts/border_recovery_stage_gate.py
```

Fixed GR III 2.10 RTOS SHA256: `8a4eafcad2716e0b21e9909264e1242e534f0e39e05cba82a53546ceb4070b67`. No GR IIIx port identity has been asserted by these tests.

## Pre-release boundary and reservation identity

Private Fill hooks original release call `0x5376a38c`, original word `0xeb001278`, through `border_recovery_fill_release_hook`. Private Resize hooks `0x53771968`, original word `0xebfff501`, through `border_recovery_resize_release_hook`.

Both use the already verified lower-frame/worker-tail/private-client contract. Fill additionally requires shared service=`*(FillContext+0xc)`, callback=FillContext+4, info=fp-0xb0. Resize requires service=`*(ResolutionConvertService+0x38)`, callback=`*(fp-0x2e4)`, info=fp-0x194. A known private request whose native call arguments contradict these identities fatally retains ownership rather than falling back into stock cleanup.

Under the original service locks, the gate verifies:

- native category is info byte+3 in0..2;
- info+0x74 indicates an active native macro reservation;
- native resource mask info+0x78 is nonzero and equals service+0x100/+0x104/+0x108 for that category;
- callback pointer at service+0x40/+0x5c/+0x78 equals the exact original callback argument;
- active reservation count byte service+0xfc is nonzero, and must equal one before hardware control observations/command.

The gate does not detach callbacks, post category/capacity semaphores, clear native ownership masks or free any memory while waiting. These native fields establish consistent stock ownership bookkeeping. **They do not retroactively prove a native semaphore acquisition succeeded if its original caller ignored a kernel error.** The original reserve/binder routines have such unchecked results; closing reservation-acquisition errors requires separate private-entry guards or stronger original-owner evidence. This limitation must not be hidden by the pre-release checks.

## Native lock ordering and checked returns

The gate follows original reserve/release ordering:

1. `0x536ae71c(service+0x90,0xffffffff)`; require returned boolean1.
2. `0x536a848c(service+0x14,5000)`; require boolean1.
3. On ordinary retry, `0x536a8544(service+0x14)` then `0x536ae870(service+0x90)`; require boolean1 for each.

Tests execute the actual four original wrappers, with only their kernel calls replaced: `0x53050c9c`, `0x53051188`, `0x530511f4`, `0x53051284`. Original wrapper logic converts kernel return0 to success1. Injected negative kernel results prove the gate never treats failed acquisition as held. If the second acquisition fails, it releases only the first acquired lock before yielding/retrying. Failed unlock fatally retains the owners and does not call native release; it cannot pretend the lock was dropped.

Service IRQ dispatcher `0x5376d0e8` and its synchronous callback forwarding take neither of these locks. A check executes actual IRQ dispatch, native callback root forwarding, FillContext callback `0x53768744 -> 0x537686c8`, and reaches event setter for FillContext+0x20/mask1 while both service locks are recorded held. Neither native lock backend is called by that path. The event kernel boundary remains explicit; no silicon interrupt is simulated.

## Exact accepted native observations

While sole-active under both successfully acquired native locks:

1. Run actual getter `0x53778490(driver)`, require0, i.e. register status bit2 is set.
2. Run original `0x53778458(driver,0)`, the native low2 read-modify-write command at register+4.
3. Run actual getter `0x53778474(driver)`, require0, i.e. status low2 is not3.

If another reservation is active, or either getter is busy, release **only** the temporary service locks, yield1, and retry the full count/identity/getter sequence. Retain the original category/capacity reservation, worker stack, private pending token, caller stacks and image owners throughout. If the second getter is busy, the next attempt rechecks sole-active and the first getter before issuing another command. No AbortMultipleImageProcess, reset or generic DMA-idle predicate is used.

The explicit contradiction test runs the original Fill wait-argument/event-clear/release-call instruction slice. Its wait boundary returns successful mask1 completion, while the actual native driver getter reads busy status0 from RAM. Execution pauses at the guard's yield; original cleanup has never been called and ownership remains intact. Only after the RAM observation changes to native-accepted status4 does the compiled guard call the stock release boundary. This demonstrates control flow rather than equating a metadata release return with idle.

After acceptance, temporary locks are successfully dropped before entering stock `0x5376ed74`, avoiding an unproven recursive-lock requirement. A new other job can reserve the shared engine after this handoff. The acceptance is the just-finished private job's observed native contract; it does not promise the global engine remains idle forever. Tests keep stock release as an explicit ABI boundary after admission; its original cleanup behavior remains separately covered in prior release research.

## Why one complete-frame private chain gate is mandatory

Two concurrently active private jobs can each reach pre-release with count2, retain their category reservations, and wait forever for the other to release. A negative test creates separate private Fill and Resize clients, workers, stack frames and categories on the same service, runs each gate to its yield, and proves count2, both pending owners, both reservations and the first held stack remain unchanged. This is safe retention, **not a usable unsynchronized production schedule**.

`M10V_BORDER_REQUIRES_SERIALIZED_PRIVATE_CHAIN` and the JSON contract therefore require one serialization gate held across the **entire frame Fill/Resize/Transfer chain**. Original ungated StillMake/native producer jobs retain stock release behavior and can reduce active count while a private gate yields. This prototype does not change their APIs or scheduling.

## Worker-owned stage CAS prototype and lifetime

The first Transfer worker allocation now grows from stock0x44 to **0x58**. Its owned job tail remains+0x44..+0x53; the extra gate word at+0x54 is initialized0 by the owned constructor. The second Transfer worker remains stock0x44. The allocation patch at `0x5369a010` is now `mov r0,#0x58` (`0xe3a00058`), replacing original `0xe3a00044`.

- `m10v_border_stage_enter(nonzero_unique_frame_token)` obtains original Transfer factory `0x5369a0e8`, reads its first worker+4, validates the owned tail tag, and uses actual Cortex-A9 atomic compare/exchange0→token on word+0x54. Contention yields1 and retries. It returns the worker handle after acquisition.
- `m10v_border_stage_leave(handle, same_token)` uses compare/exchange token→0. A wrong owner cannot clear another frame's gate.
- Tokens must identify a live frame uniquely; a shared film ID is insufficient. Enter occurs only in worker phase, never the capture submission hook. Off must not call the stage API or native factory. Leave is authorized only after all synchronous private jobs and their callbacks have completed.

Five checks execute native singleton getter/guard logic, compiled atomic CAS contention and handoff, wrong-owner release, zero-token no-factory path, initialized constructor word and invalid-tail rejection. The builder rejects mutable static data/BSS/TLS.

Original factory is at static `0x5536c00c`, guarded by `0x5536c018`; its guarded getter registers destructor `0x53699ed0` via `0x5313fbb8`. This is long-lived original worker storage during normal runtime, rather than a menu page allocation that disappears on UI close. However, both destructor `0x53699ed0 -> 0x53699e7c` and explicit virtual factory Destroy `0x53699f1c` can delete the worker. They do **not** read the appended CAS word or acquire a new lifetime lease.

A negative lifetime test executes original factory Destroy with a held stage token71 and records that it still invokes the worker's deleting destructor and clears factory+4. The deleting endpoint is replaced in the test to avoid freeing fixture RAM. **No native factory teardown may occur while private stage owners or waiters exist.** The stage API shares the original worker's lifetime prerequisite; it does not independently prevent teardown. Startup/init ordering, native service teardown/shutdown quiescence, physical pixels/cache and performance remain required integration/acceptance evidence before activation.
