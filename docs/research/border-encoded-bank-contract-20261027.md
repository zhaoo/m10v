# Encoded bank and fourth JPEG channel

Hash-pinned original GR III 2.10 and GR IIIx 1.60 ARM metadata execution.
No JPEG pixels, pool allocation, hardware response or camera performance is
executed. All selected instruction spans match between the two official inputs.

## Original query and layout

The probe executes `53510cec -> 53664c0c -> 536a2a30/53664b88`, not a
zero-return substitute for the encoded query. Public getter `5350d47c(id4)`
reads `R+360`; public setter `5350d7e8(id4)` stores `R+300` and dispatches
through the original vtable to `53510fa0`. That method initializes encoded
output controls at `R+130/+148/+160/+178`, each with pointer `+0`, target
bytes `+4`, capacity `+8`, encoded length `+c` and format/control fields.

The fixture supplies frozen SI size enum0, aspect0, crop float1.0, raw height4000
and explicit initialized extra-size singleton metadata with crop1.0. Thumbnail
geometry service alone is a declared160x120 boundary. The native size selector,
capacity arithmetic and layout execute from original instructions. The helper's
singleton initialization/thread ownership is not proved by these supplied fields.

For6000x4000, bank base `0x60000000`:

| Channel | Control | Offset | Target bytes | Capacity |
| --- | --- | ---: | ---: | ---: |
| Main | R+130 | 128 | 13,714,288 | 15,085,728 |
| Preview | R+148 | 15,086,016 | 56,320 | 64,512 |
| Thumbnail | R+160 | 15,150,656 | 7,168 | 8,192 |
| Extra | R+178 | 15,158,976 | 3,000,000 | 3,300,000 |

The allocation query is **15,159,200** when `*(R+5c)+d` is0. Extra's control
is populated even though its region is outside that query. This is an inactive
channel, not an allocated fourth output. When that flag is1, query capacity is
**18,516,800**, covering extra and a separately positioned57,600-byte RGB
thumbnail workspace (`R+194` pointer, `R+1a4` length). Active output intervals
fit the query in these fixtures; a query is not proof of physical pool capacity.

## R110 and actual request bounds

Original Setup6 fragment `5350ea50..5350eab8` copies the source image descriptor
`R+70` into `R+110` via `536a3d84`, then binds four sources and four controls:
`[Rb0,Rd0,Rf0,R110] -> [R130,R148,R160,R178]`. The probe executes this fragment.
`R110` retains a separate descriptor and must be updated before that copy or
repaired at the established boundary when source geometry changes.

Actual capture packet construction `5350480c..53504890` loads flag
`*(R+5c)+d` and writes it to codec packet `+23`. Original codec service checks
that enable at `53663fdc`; when nonzero its branch `5366437c..5366438c`
encodes source3 into control R178. Thus the same flag controls allocation and
fourth-channel submission. The probe executes the capture packet construction;
the asynchronous codec dispatcher/scheduler itself is not executed.

For both main and enabled extra, original request builder `53663a8c` loads
control `+8` and places it in engine packet `+14`; output pointer comes from
control `+0`. It passes the source's actual width/height separately. The probe
also executes original engine driver `53791044`, with start/control services
substituted and MMIO backed by RAM: `53791188` shifts capacity right9, then
actual setter `53792394` writes that sector count to `0x298c0458`.

Main's fixture limit serializes as29,464 sectors (**15,085,568 bytes**); extra
as6,445 sectors (**3,299,840 bytes**). Each is rounded down to512 bytes.
This proves the bound's serialization, not the silicon's enforcement or error
handling. The prototype does not generate a successful JPEG or fake its length.

## Expanded geometry does not enlarge encoded storage

Changing only source/main geometry to6320x4640, while preserving frozen SI,
leaves original id4 query and all four output capacities **unchanged**. The
original request builder/driver still serializes that larger width/height and
the old capacity. No native dimension-versus-capacity assertion rejects this
fixture. Absence of such an assertion does not establish safe physical writes.

For comparison, execute native policy helpers `53664954` and `53664b88`
directly with explicit outer dimensions, without inventing a new SI enum:

| Dimensions | Native main target/capacity | Native extra target/capacity |
| --- | ---: | ---: |
| 6000x4000 | 13,714,288 /15,085,728 | 3,000,000 /3,300,000 |
| 6320x4640 | 16,757,040 /18,432,752 | 3,665,600 /4,032,160 |
| 6480x4480 | 16,588,800 /18,247,680 | 3,628,800 /3,991,680 |

These values reproduce the original target/capacity policy; they are **not
worst-case JPEG sizes or a guarantee of quality/compressibility**. Simply
increasing main's old capacity to18,432,752 crosses the next preview region.
Increasing extra's old capacity to4,032,160 exceeds the18,516,800 bank by674,336
bytes, before considering the existing RGB thumbnail workspace. Neither change
is admissible without a new fully bounded placement and actual owner capacity.

## Admission before enabling

Keep each active output's pointer8-byte aligned and its serialized512-byte bound
inside its actual reserved slice. Validate those slices and the RGB workspace
against the **actual allocated owner's interval**, not only `R+360` or a later
size query; retain owners through completion. An inactive R178 descriptor must
not be submitted merely because its pointer exists.

With unchanged encoded storage, do not raise capacities, assume white borders
compress well, or claim that a completed-length check can undo an earlier
overrun. Establish native hardware bound enforcement and the encoder's bounded
overflow/quality-retry/failure path before accepting a larger raster. A valid
nonzero length must remain within the serialized bound; overflow/zero/error
must preserve ownership and use a proved recovery route. These are still gates.
No new encoded storage, source pixel work, RAW mutation or CPU fallback is
implemented by this research.

## Reproduction

Restore official fixtures using `gr3-gr3x-border-iip-20261027.md`, then:

```sh
/Users/zhaoo/Desktop/code/zhaoo/m10v/.venv/bin/python -m unittest tests.test_gr3_border_encoded_bank -v
/Users/zhaoo/Desktop/code/zhaoo/m10v/.venv/bin/python scripts/probe_gr3_border_encoded_bank.py --model gr3 --rtos builds/gr3-border-iip-20261027/gr3-official-rtos.bin --out builds/gr3-border-iip-20261027/gr3-encoded-bank.json
/Users/zhaoo/Desktop/code/zhaoo/m10v/.venv/bin/python scripts/probe_gr3_border_encoded_bank.py --model gr3x --rtos builds/gr3-border-iip-20261027/gr3x-official-rtos.bin --out builds/gr3-border-iip-20261027/gr3x-encoded-bank.json
```
