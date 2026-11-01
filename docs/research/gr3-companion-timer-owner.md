# GR III 2.10 companion owner timer route

2026-11-01. Read-only firmware research and ARM characterization tests; no camera writes or production owner adapter enabled.

## Pinned input and native ABI

Decoded official RTOS SHA256: `8a4eafcad2716e0b21e9909264e1242e534f0e39e05cba82a53546ceb4070b67`. Addresses below apply only to that image. `scripts.analyze_gr3_settings.read_firmware` rejects any other hash.

| Function | Address / ABI |
| --- | --- |
| Timer model getter | `0x5320b01c(root)` → singleton `0x55063edc`, initialized guard `0x550645ac` |
| One-shot start | `0x5322b468(model, delay, callbackObject)` → timer ID; callback vtable method at byte offset `+8` |
| Cancel | `0x5322b1ec(model, timerId)` → 1 for a matching record, 0 otherwise |
| Timer-task run | `0x5322b17c(model)`; waits on model `+0x2c`, posts event `0x199` with source `model+0x28` |
| Queue getter | `0x5320aefc(root)` → singleton `0x550645f0`, guard `0x55063e54` |
| Queue enqueue | `0x532288b0(queue, eventId, payload, source)`; copies a 12-byte event and signals queue `+8` |
| AppMain run | `0x53207e88`; repeatedly gets the queue and calls drain `0x53228b08` |
| Event delivery | `0x53228ab4(queue,event)`; event `0x199` skips ordinary BaseController dispatch and invokes `source->vtable[0](source,id,payload)` |
| Model callback | `0x5322b53c` subtracts `0x28`, branches to `0x5322b52c`, accepts only `0x199`, then sweeps at `0x5322b4b4` |

`AppMain` identity is anchored by RTTI string `7AppMain` at `0x53b4daf8` and vtable `0x53b4db10` containing destructor entries and run `0x53207e88`. Drain unlocks its ring mutex at queue `+0x24` before event delivery; its outer model serialization mutex at queue `+0x38` remains held. Normal UI dispatch `0x5316d5dc` is called by the same native event delivery path for other event IDs.

The timer sweep at `0x5322b4b4` checks that ID and callback are nonzero and the AlarmTimer has expired. Instructions `0x5322b500–0x5322b518` load ID/callback, clear **both record fields before invoking** `callbackObject->vtable[+8](callbackObject,timerId,callbackObject)`. Rearming from the callback can therefore reuse the cleared record. Cancel stops its AlarmTimer and zeroes record ID and callback at `0x5322b250/0x5322b254`. An already queued model event does not retain the canceled private callback.

Stock lifecycle examples: `0x531ce2c8–0x531ce2dc` gets the model, starts delay `0x1388` with callback subobject `this+0x158`, and stores the ID at `this+0x168`. `0x53176e38–0x53176e4c` cancels a saved timer and clears its ID. Delay units have not been proven: `0x1388` must not be presented as a measured number of milliseconds.

## Selected integration strategy and remaining ownership gap

Use one native one-shot timer, started through existing TopMenu constructor hook `0x5316fcf8`, to poll a bounded companion mailbox. The callback executes commits on AppMain, through the existing library/settings mutation contracts, and rearms once after a bounded amount of work. Do not call RTOS functions from Linux, inject keys, hook capture, or use a busy loop to wake the owner.

Select a **permanent extension-reserved mailbox and callback control object**, independent of the TopMenu heap lifetime. Store only the current owner pointer, owner epoch, enabled flag and timer ID in the control object; inspect/dereference the owner only on AppMain. Linux writes only fixed-size mailbox payload storage, after an explicit boot/lease handshake, and never writes the heap pointer or lifecycle control fields. No memory address is allocated or approved by this research: exact reserved placement, image-size/relocation audit, cache-line separation and Linux-to-RTOS cache publication remain implementation blockers.

TopMenu destruction must first disable/revoke the owner epoch, then cancel the timer and clear the owner reference before destroying its settings pages. Because timer events refer to the permanent native timer-model source, pending event199 sweeps can safely observe a cleared timer record. The permanent mailbox avoids a Linux writer racing a freed TopMenu tail. Leases, duplicate/request-sequence handling and capture-busy rejection still belong to the companion transaction protocol; this route does not establish them.

## Executed evidence

`tests/test_gr3_companion_timer_arm.py` executes actual pinned ARM getters, native start/cancel, timer task enqueue, AppMain run, queue drain, event199 dispatcher and timer expiry sweep in Unicorn. Only native OS mutex/semaphore and AlarmTimer methods are mocked. An ARM observation callback is reached through the native chain, records cleared fields at entry and optionally calls native start to rearm. Tests stop after queue draining, before unrelated controller rendering.

Four checks pass:

1. Timer expiry reaches the observation callback through AppMain, with model serialization mutex held and ring mutex unlocked; ordinary BaseController dispatch is skipped.
2. Both record fields are zero before callback entry; a callback can rearm through native start and obtain a new ID.
3. Cancel clears the callback pointer; a previously queued model sweep does not dereference invalidated callback storage.
4. A wake while the AlarmTimer remains active does not invoke the callback.

Sensitivity check: in private emulator image copies, replacing either the expiry callback-pointer clear at `0x5322b504` or cancel callback-pointer clear at `0x5322b254` with NOP makes the corresponding assertion fail (`1442841600 != 0`). The pinned source and repository production code were never mutated. This is characterization of existing firmware rather than a claim of test-first production implementation.

Run with `M10V_GR3_ORIGINAL_RTOS=/absolute/path/to/official-rtos.bin python -m unittest tests.test_gr3_companion_timer_arm -v` from repository root. Requires Unicorn and the existing ARM assembly helper's clang toolchain. Missing official input explicitly skips the tests; a different hash fails closed.

`npm test` was also run in the managed checkout: 450 tests, 249 passed, 143 failed, 58 skipped. It is not a green suite. The checkout lacks official firmware inputs and `.venv/bin/python` / `.venv/bin/python3.12`; the log also includes baseline expectation failures such as `old web configuration migrates into v4 and validates effect ranges`, `requested groups retain stock identities`, and `imaging switches survive draft and undo normalization, including border and A/B`. No fixes outside this research scope were attempted. Complete failure names and details are retained locally in `/tmp/m10v-owner-timer-npm-failures.txt` and `/tmp/m10v-owner-timer-npm-test.log`.

These are offline instruction/lifecycle results. Physical timer scheduling and delay units, teardown on the camera, reverse cache coherency, authenticated mailbox writes, configuration persistence, App reload and wireless compatibility remain unvalidated.

## Exact 16-byte entry preimages

| Entry | First 16 bytes (hex, file byte order) |
| --- | --- |
| `0x5320b01c` | `0dc0a0e118d82de9ac4504e3064545e3` |
| `0x5322b468` | `0dc0a0e178d82de90040a0e104b04ce2` |
| `0x5322b1ec` | `0dc0a0e118d82de904b04ce23c3090e5` |
| `0x5322b4b4` | `402090e50dc0a0e178d82de904b04ce2` |
| `0x5322b52c` | `993100e3030051e11eff2f11ddffffea` |
| `0x5322b53c` | `280040e2f9ffffea0dc0a0e178d82de9` |
| `0x53207e88` | `0dc0a0e100d82de904b04ce2bb0b00eb` |
| `0x53228b08` | `0dc0a0e1cc3d0ee3f0df2de97c9705e3` |
| `0x53228ab4` | `b020d1e10dc0a0e118d82de9993100e3` |
| `0x532288b0` | `0dc0a0e1f0df2de97c6705e3056445e3` |
| `0x5322b17c` | `cc3d0ee30dc0a0e1d53345e32c4080e2` |
| `0x5320aefc` | `0dc0a0e118d82de9544e03e3064545e3` |
