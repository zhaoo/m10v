# Owned native client and Transfer worker wait guard prototype

Status: isolated module and sixteen original-ARM hook-prototype checks pass. No production builder references this module; no camera activation, firmware artifact or commit is included. This is GR III 2.10 only and uses the fixed RTOS SHA256 `8a4eafcad2716e0b21e9909264e1242e534f0e39e05cba82a53546ceb4070b67`.

Artifacts:

- `native/gr3/m10v_border_wait_guard.c/.h`: freestanding native client, pending/callback lifecycle, outer wait guard, extended first Transfer worker constructor/body/wait guards.
- `scripts/border_recovery_wait_guard.S`: ABI adapters for existing worker body and wait call sites.
- `scripts/border_recovery_wait_guard.py`: builds the isolated ARM code into temporary memory and executes the original firmware caller/constructor/dispatcher/wait paths with narrow hardware/RTOS test doubles. Allocated mutable ELF sections are rejected: there is no static mutable registry or TLS state.
- `scripts/border_recovery_client.c/.py`: earlier standalone client probe (five checks), retained as focused pending/inflight evidence.

```sh
/Users/zhaoo/Desktop/code/zhaoo/m10v/.venv/bin/python scripts/border_recovery_wait_guard.py
```

## Why the previous callback-inflight field was insufficient

The creative codec's existing private `cr_client` wrapper increments inflight during notification and waits for it before destruction. Before any callback begins, however, inflight is zero even while a queued worker still references caller descriptors. It does not prove the worker request has completed.

The prototype adds a **pending job token set before enqueue**. The custom native vtable callback increments inflight, invokes real `0x534aab0c`, and clears pending only for the configured exact completion event **after the real notifier returns**. It then decrements inflight. Destruction requires both pending and inflight zero. An unrelated callback never completes the job. Only this privately owned object's vtable identity is checked before reading appended fields; a stock 32-byte native client is not read past its original shape.

The common native callback maps Transfer completion `0x03050006` to event bit `0x400` at client `+4`, at original `0x534aac68..0x534aac70`. Tests inspect pending=1/inflight=1 inside the actual native signal boundary, then verify both reach zero only after callback return. The client should be newly owned for one serialized operation; no claim of protection against duplicate stale hardware completion or concurrent unrelated use is made.

## Both original caller frames must stay alive

Same-format public operation `0x534ab7a0` stores its descriptor pair at `fp-0x7c` and job object at `fp-0x68`. It calls `0x534aad6c` at `0x534ab8c0`. The common dispatcher wait at `0x534aae28` calls `0x536a9e8c(client+4,mask400,NULL,timeoutFFFFFFFF)`, ignores its result, clears the event, and returns at `0x534aae48`; public operation then returns at `0x534ab848`. Without a guard, a failed wait unwinds both frames while the original worker can still reference the pair/job.

Replacing only the common wait call with `m10v_border_client_wait` retains both original frames. Private clients wait until pending and inflight are zero even if the kernel wait returns error. Stock clients call the original wait once with their exact original arguments.

After a successful wait consumed the completion event, the guard **yields for the notifier tail instead of waiting on the same event again**. Rewaiting after event consumption could deadlock because the callback finishes without emitting a second event. Kernel failures while no callback is in flight cause an infinite retry through the native wait with timeoutFFFFFFFF; a yield precedes retries. A failure counter is diagnostic only and never authorizes return/free/next recipe.

The original-public-operation test patches this call in its in-memory ROM fixture, runs `0x534ab7a0 -> 0x534aad6c -> guard`, forces wait failure, and stops at the first yield. It verifies the enqueued job and descriptor pair remain inside the held original stack, neither original return PC ran, and pending is still one. It executes the full custom wrapper plus real native callback on an independent callback stack, proves all held caller stack bytes remain unchanged, then resumes original event clear and both returns. No worker/DMA or pixels are simulated by the queue test double.

## First Transfer worker size and exact call-site contracts

Original factory `0x53699fc4` allocates first worker **0x44 bytes** at `0x5369a010` and calls constructor `0x5369a2c0` at `0x5369a01c`. The second worker is separately allocated 0x44 bytes at `0x5369a060` and constructed by `0x5369aedc`; this prototype leaves it unchanged. First worker event object begins at `+0x38`; stock allocation ends at `+0x44`.

The first allocation must grow to **0x58 bytes before construction**. The new wrapper calls the exact original constructor and initializes a 16-byte appended tail at `+0x44..+0x53`: tag, private client pointer, job pointer, active flag. It does not repurpose unknown stock padding. The gate word at `+0x54` initializes zero and a canary at `+0x58` remains untouched in the constructor test. This cannot safely be installed after an existing stock-sized worker was already created.

| Original patch address | Locked original word | Prototype replacement |
| --- | --- | --- |
| `0x5369a010` | `0xe3a00044` | `mov r0,#0x58`, only the first allocation |
| `0x5369a01c` | `0xeb0000a7` | call `m10v_border_transfer_construct` |
| `0x5369ac4c` | `0xebffff3d` | call assembly `border_recovery_transfer_body_hook` |
| `0x5369a478` | `0xeb003e83` | call assembly `border_recovery_transfer_wait_hook` |
| `0x534aae28` | `0xeb07fc17` | call `m10v_border_client_wait` |

The factory test executes actual original factory setup with only allocation, service lookup, assertions, and task-start boundaries explicitly replaced. Its first allocation is 0x58, second remains0x44, first original constructor executes, new tail is initialized, and both workers retain the original shared TransRectService pointer.

At `0x5369ac4c`, original dispatcher has r0=worker, r1=descriptor pair, and **r4=current job**, where job `+4` is caller's native callback object. The assembly hook passes r4 as third argument to the body wrapper. For an exact private pending Transfer client, the wrapper stores worker/job identity in the owned tail, invokes original `0x5369a948` once, then clears the tail **before** original dispatcher publishes final caller completion.

The dispatcher test executes actual `0x5369abc8`, patched call-site assembly, the compiled body wrapper, actual final virtual callback dispatch, custom client wrapper and original `0x534aab0c`. Only the original hardware-copy body is a boundary double. It observes the exact bound tail during the body and the cleared tail before outer callback signals400. This does not claim the hardware-copy body itself was executed by this particular test; the separate copy analysis covers packet construction.

At `0x5369a478`, original registers r0..r3 hold wait arguments and **r5 is worker**. The assembly wrapper passes r5 as the fifth C argument while maintaining ARM stack alignment and original callee-saved registers. The compiled guard protects only a validated active appended tail whose private client is pending and whose worker/job/caller pointers all match. It repeats failed waits and requires the entire native completion mask `0x03050001` in the output word before allowing original per-plane clear/stop/next-plane flow. Stock requests retain the original single-wait behavior.

## What remains outside this prototype

This module prevents timeout/error return from dropping known caller/worker ownership on the verified Transfer path. It is not an abort/reset acknowledgment and does not claim silicon idle or correct DMA pixels. Native events and queue/kernel services in tests are explicit doubles; no fake pixels or physical performance are generated.

The final isolated prototype additionally guards the verified Fill and Resize wait paths described below. Outer client protection alone cannot distinguish a worker that falsely publishes completion; the matching worker-specific hooks and allocation changes are mandatory. This remains wait-error retention, not a proof of IIP release idle acknowledgment.

Before any activation: integrate preimage/relocation/model identity checks in the central builder, ensure first allocation/constructor patch runs before singleton worker construction, preserve all live stack/descriptor/plane owners through both guards, validate event freshness and actual DMA/cache behavior, and independently close Fill/Resize safety and memory/performance acceptance. An indefinite failure hold is a fatal ownership safeguard; it is not a normal latency workaround or proof that timeout recovery succeeded.

The eighth check explicitly pauses the real custom/native notification inside its event setter (pending1/inflight1), runs the outer guard with a successful consumed event, pauses its yield, then completes the actual callback tail on its saved independent CPU context. Resuming the outer guard returns with exactly one native wait call. This exercises the consumed-event/no-second-wait rule rather than merely asserting its source code.

## Fill and Resize extension: owned tails and verified parent frames

The prototype now covers the original Fill and Resize worker wait paths without a static registry or TLS. All appended tails are explicit allocation extensions, created before worker singleton initialization:

| Worker | Original allocation | New allocation | Appended tail | Exact outer completion/mask |
| --- | --- | --- | --- | --- |
| First Transfer | 0x44 | 0x58 | +0x44..+0x53 | 03050006 / 400 |
| FrameOperationPipeService Fill | 0x58 | 0x68 | +0x58..+0x67 | 03070004 / 10 |
| ResizeFactory +0xc Resize worker | 0x48 | 0x58 | +0x48..+0x57 | 03020002 / 40 |

Fill factory `0x53658988` is executed with its patched allocation/constructor in the new factory test: actual allocation asks for0x68, original constructor `0x53658c78` executes, worker+0x44 receives the singleton FillContext, and appended ownership tag is initialized. Resize factory `0x536729ec` allocates three worker shapes: +4=0x60 at `0x53672adc`, +8=0x4c at `0x53672b4c`, +0xc=0x48 at `0x53672bac`. Only the last grows to0x58. Its original allocation/constructor slice executes in a test, while the first two allocation instruction preimages are verified unchanged.

Actual original OnMessage dispatchers are tested with the body-hook prototypes. Fill dispatcher `0x5365935c` calls its body at `0x536594a0`, with worker r0, params r1, current job r4. Resize dispatcher `0x53673f48` calls its body at `0x53674014`, with the same job-register contract. The corresponding body wrapper binds only the exact private pending client/event/mask into its owned worker tail, invokes the original body once, clears the tail after body return, and allows the original dispatcher to invoke final client notification. Tests execute both real dispatchers, assembly hooks, compiled body wrappers, real virtual notification and native `0x534aab0c`; hardware body invocation is the explicit boundary double.

### Fill inner wait

Original lower `0x53769a78` saves caller r5 at `fp-36`, saved LR at `fp-4`. The only admitted saved LR values are **0x536591cc** (striped Fill call) and **0x53659258** (small Fill call). Real original lower-prologue execution verifies these save slots. The guard checks LR before dereferencing the saved caller r5 as a worker; an invalid-LR test supplies an unmapped saved worker pointer and proves single-pass stock wait without dereferencing it.

The saved r5 must have an active owned Fill tail, exact current private client/job identity, and `*(worker+0x44)==FillContext`. Original wait uses **event FillContext+0x20, mask1**, notmask4. This follows `r8=1` at `0x5376a210` and `sb=FillContext+0x20` at `0x5376a240`. The assembly adapter passes original fp and r6 (FillContext) to the compiled guard. The original output pointer is NULL, so the guard supplies its own local word only for an owned request to verify actual event bits; stock clients keep their exact original ABI.

The new test executes the original prologue, then original pre-wait instruction slice through the patched `0x5376a370` call, injects failed then successful wait, and stops at `0x5376a374` before event clear/release. Both admitted saved LR paths pass and no release is entered prematurely. Graph/image construction and silicon are outside this bounded slice.

### Resize inner IIP and equal-size DMA paths

Original lower `0x53770bf0` saves caller r7 at `fp-28` and LR at `fp-4`; it preserves its original context argument at `fp-0x2d0`. The only admitted Resize call returns to **0x536733e4**, from `0x536733e0`; caller sets third argument2 at `0x536733b4`. Guard requires saved worker r7 have an active owned Resize tail and `*(worker+0x34)==saved context`, with event=context+0x48 and mask4.

A test executes the real original lower prologue with Cortex-A9 VFP context enabled, checks those exact save slots, then runs the real wait-argument setup and patched call at `0x5377160c`, forcing an error followed by actual mask4 completion. It returns to `0x53771610` only after success. No speculative worker pointer is accepted based on stack padding or a global singleton alone.

Resize body also takes a DMA shortcut for equal dimensions/compatible format. Those waits use worker+0x3c, mask3, with worker retained in r7, at `0x53673244`, `0x5367331c`, and `0x53673384`. All three must be guarded: otherwise a private Resize operation could still unwind through the shortcut after failure. Tests patch and execute each real BL instruction through its assembly adapter, injecting failed then mask3-complete waits. Original Resize DMA callback `0x53672dcc` accepts the two native completion IDs and sets fullmask3 at worker+0x3c.

Additional locked patch contracts:

| Address | Original word | Isolated replacement |
| --- | --- | --- |
| 536589fc | e3a00058 | mov r0,#68 |
| 53658a08 | eb00009a | m10v_border_fill_construct |
| 536594a0 | ebfffed9 | border_recovery_fill_body_hook |
| 5376a370 | ebfcfec5 | border_recovery_fill_wait_hook |
| 53672bac | e3a00048 | mov r0,#58 |
| 53672bb8 | eb000094 | m10v_border_resize_construct |
| 53674014 | ebfffc1f | border_recovery_resize_body_hook |
| 5377160c | ebfce21e | border_recovery_resize_wait_hook |
| 53673244 | eb00db10 | border_recovery_resize_dma_wait_hook |
| 5367331c | eb00dada | border_recovery_resize_dma_wait_hook |
| 53673384 | eb00dac0 | border_recovery_resize_dma_wait_hook |

Hexadecimal values in this table have their `0x` prefix omitted for readability; allocation values68/58 mean0x68/0x58.

**Remaining safety scope:** these hooks prevent kernel/event wait errors from releasing known owned workers, stack jobs and buffers. They do not independently intercept original IIP release's later idle-poll timeout after an apparently successful completion event. As separately proven, that release may log-and-continue while status remains busy. Contradictory completion-versus-status behavior, device event freshness, proper error flags, hardware pixels/cache, memory and performance remain explicit gates before any activation. No native abort/drain acknowledgment is invented by this wait-retention module.

## Final pre-release and stage-gate extension

The prototype now also contains private Fill/Resize pre-release driver-condition gates and an explicitly allocated complete-frame CAS gate in first Transfer worker+0x54. **Final Transfer owned allocation is0x58, not the earlier0x54 tail-only size.** See `border_recovery_release_gate-20261027.md` and `scripts/border_recovery_wait_guard_contract.json` for exact native lock/ownership checks, the contradiction test, serialized-private-chain requirement and native teardown lifetime limitation. No abort acknowledgment or silicon drain has been asserted. The native semaphore-acquisition-error limitation remains explicitly documented there.
