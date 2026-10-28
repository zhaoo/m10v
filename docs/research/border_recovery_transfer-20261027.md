# Original TransRect DMA completion and failure retention

Status: seven original-ARM CPU-control-flow checks pass. This establishes service ownership and failure boundaries, **not silicon stop/drain acknowledgment or physical pixel output**. No hardware activation, native pipeline edit, package or commit.

Input: GR III 2.10 RTOS `builds/gr3-extension-validation/official-rtos.bin`, SHA256 `8a4eafcad2716e0b21e9909264e1242e534f0e39e05cba82a53546ceb4070b67`.

```sh
/Users/zhaoo/Desktop/code/zhaoo/m10v/.venv/bin/python scripts/border_recovery_transfer.py
/Users/zhaoo/Desktop/code/zhaoo/m10v/.venv/bin/python scripts/border_recovery_transfer.py --disassemble
```

The script reuses only the hash-locked original ARM harness from `border_recovery_contract.py`; it does not edit or depend on the copy agent's implementation. Registers are ordinary RAM and no image plane is mapped. Exact instruction bytes/range hashes are emitted by `--disassemble`, with a local copy at `builds/border_recovery/transfer-control-flow.txt`.

## Concrete stop behavior

Per-plane routine `0x5369a40c` clears worker event `worker+0x38`, mask `0x03050001`, calls native submit `0x537e2814`, waits at `0x5369a478` through `0x536a9e8c`, then **does not inspect r0**. It clears the event at `0x5369a488`, calls `0x537e29e4(*(worker+0x34),0)` at `0x5369a494`, and returns. Timeout input `*(0x53d5edcc)` is `0xffffffff` in this fixed ROM. A failed wait therefore denotes an RTOS/service failure rather than a demonstrated finite deadline expiration under the original arguments. Tests force return 0/1/0xffffffff as explicit service doubles; every result follows the same cleanup path.

`0x537e29e4(service, channel)`:

1. Calls IRQ-manager `0x53784de0(manager=*(service+0x18), id=0x6f, mask=1 or 0x10)`.
2. Calls native driver `0x537e2ea4` with selected channel object and value zero. Driver code reads its register-root pointer, reads only channel register `+0`, clears low2 bits by read-modify-write, returns.
3. Calls reference-counted clock-access helpers `0x537e23f0(service,0)` and `0x537e2550(service,0)`, decrementing service bytes `+0x60/+0x61`; only transition to zero invokes ImageClockService `0x5377c648` for flags2/8.
4. Calls original callback detach `0x53562910(service+0x1c or +0x38)`, clears its current callback pointer, and posts its ownership semaphore.

There is **no channel-status acknowledgment or polling loop** in this stop path. An executable memory-read trace through the real stop/driver/refcount/detach code observes exactly one read from the selected channel register image: control at `+0`. Neighbor words initialized to `0xdeadbeef/0xcafebabe` remain untouched; IRQ and top-clock backends are named doubles, so no hardware response is invented. The callback detach itself executes original code, with only its RTOS semaphore post replaced.

The native register factory `0x537e3668..0x537e367c` sets driver `+0x14 = 0x288c000c` and `+0x18 = 0x288c0050` (literal at `0x537e36c0`). Driver dump names `0x288c0000` as `SR`, +4 `XCHICE`, +8 `XCHICF`, +0xc first-channel `XTRG`, +0x50 second-channel `XTRG`. Names and readback are not idle semantics. The inspected driver exposes setters, checksum access and dump, but no verified DMA-busy/idle getter was identified. **Do not import IIP status predicates into this engine.**

## Ownership and callback delivery

The original bind helper `0x5356284c(callback_root, caller)` waits through `0x536b00c8(callback_root+8,0xffffffff)` **before** storing caller at root `+4`. Native submit `0x537e2814` invokes it before packet serialization or entering hardware start `0x537e25fc`.

- Channel0 root: service `+0x1c`; current callback: service `+0x20`; ownership semaphore: service `+0x24`.
- Channel1 root: service `+0x38`; current callback: service `+0x3c`; ownership semaphore: service `+0x40`.
- Detach `0x53562910` clears root `+4/+0x14`, then posts root `+8` via `0x536b0014`. It does not wait for DMA idle.

The competing-request test executes original submit/binder until entry to the semaphore wait and stops there. The old callback pointer is still installed, and hardware-start address `0x537e25fc` was never reached. Thus retaining this original reservation can block the next legal same-channel request before it starts. This conclusion assumes successful native semaphore behavior; kernel scheduling/error semantics are outside the test. Direct branch locators find hardware-start calls only from native bind-first adapters `0x537e27d4`, `0x537e2814`, `0x537e2920`; indirect callers have not been globally excluded.

IRQ service `0x537e22a0` recognizes ID `0x6f`:

- mask0x1 => callback root service `+0x1c`, message `0x020a0001`;
- mask0x10 => root service `+0x38`, message `0x020a0002`.

`0x535628dc` invokes the installed object's vtable `+8` synchronously. For the first TransferRect worker, thunk `0x5369a2b8` adjusts `this -= 4`, then callback `0x5369a244` accepts both messages and directly calls `0x536a9d1c(worker+0x38,0x03050001)`. A full original ARM test executes dispatcher → callback indirection → worker callback → event boundary, with only the event kernel wrapper replaced. **There is no queued callback message at this inspected layer.** After signaling, the worker callback only returns; original callback wrapper then writes a return value into the persistent callback-root object. This narrows the lifetime problem but does not prove hardware pending-bit acknowledgment, duplicate-event suppression or absence of an in-progress IRQ on another CPU.

## Safe failure-retention candidate boundary

Hook **`0x5369a47c`**, immediately after the event wait and **before** the second event clear. At this boundary:

- r0 is still the wait return; output event word is at `fp-0x24`.
- r5 is worker, r6=`worker+0x38`, r7 is native 0x18-byte per-plane transfer packet.
- service=`*(worker+0x34)`; the original worker stack and outer per-plane/copy frame remain live.
- callback semaphore is still reserved; stop/detach has not returned it, and current engine clock references remain live.

The retention test forces failed wait, executes to this exact PC, and proves original stack remains allocated, only the initial event clear occurred, and stop has not run.

A failure-only adapter can retain this worker/frame, source and destination owners, packet, callback reservation and engine references, and refuse to advance plane/recipe or publish caller completion. It may wait again for the original completion event while preserving ownership. A deadline may report a fatal error and require restart, but **cannot free/reuse buffers or call stop-and-return on busy**. This is a fatal data-lifetime safeguard, not a normal performance workaround. A buffer-only quarantine after the stock helper returned is insufficient because the stock helper already detached ownership and continued to subsequent planes.

Ordinary continuation should require successful wait plus the required original event bits, then preserve the original stop/cache/outer-completion sequence. This uses the native completion contract; it does not assert a hardware stop acknowledgment. The public TransferRect dispatch's caller context and all descriptors must remain alive for the entire worker request. A caller timeout must not unwind/free those owners while the worker is retained.

Remaining proof before hardware activation: fresh-event attribution and physical pending-bit behavior; caller-task timeout/lifetime behavior when worker is retained; exclusive channel reservation error semantics; actual pixel/stride/cache behavior; and physical performance. The identified path can avoid generic IIP ownership for copying, but it does not by itself close FillRectIip failure safety.

## IRQ-manager acknowledgment ordering is now executed

Original handler `0x53787b44` reads pending `0x288c0008 & 0x11` via `0x5378fd34`, saves it, and calls `0x5378fd48` to **write those exact pending bits back to 0x288c0008 before dispatch**. It then reads enable `0x288c0004 & 0x11` via `0x5378fd20`, intersects saved pending with enable, and if nonzero tail-calls manager vtable `+0x18` with `(manager, 0x6f, pending & enable)`. Zero pending or a zero intersection produces no dispatch.

The seventh test runs this real handler plus real register readers/writer against ordinary RAM, records memory writes, and replaces only the final manager callback. It proves ACK-write-before-callback order for channel0, channel1, both channels, zero pending, disabled completion, and partial enabled masks. The RAM model does **not** implement write-one-to-clear behavior; it records the command exactly. Together with the synchronous callback test this closes the CPU-ordering path from native pending acknowledgment command to worker completion event. Physical pending clearing and absence of stale/duplicate IRQs remain device evidence.

Mask-helper caveat: stop's `0x53784de0` case6f at `0x53785fd4` reads native enable, computes `old & ~mask`, and forwards to `0x5378fcf4`. That low-level function reads current `0x288c0004 & 0x11`, ORs it into its argument, then writes the result. Thus an ordinary RAM replay must not manufacture a successful enable-bit clear or infer interrupt drain simply from the helper name. The completion retention route is based on keeping the original callback reservation and owners, rather than assuming this mask helper guarantees drain.
