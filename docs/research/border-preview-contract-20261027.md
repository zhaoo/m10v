# Border preview publication and lifetime contract

Read-only research, 2026-10-27. GR III2.10 decoded RTOS SHA256 `8a4eafcad2716e0b21e9909264e1242e534f0e39e05cba82a53546ceb4070b67`, inspected at `/tmp/m10v-800t-analysis/rtos.bin`. No code activation, test firmware, hardware or publication. IIIx must independently retain the existing strict model-difference port; this report does not certify IIIx display hardware.

## Main finding

There is a concrete original immediate-review handoff from **recipe+0xb0**, through two copied request descriptors, into a Playback-owned persistent descriptor. `recipe+0x110` is the separate extra-JPEG source copied by JPEG Setup6; the inspected code does **not** establish it as the immediate-review source. Earlier prose calling0x110 an immediate-review buffer is insufficient evidence for a dimension-changing feature.

The main descriptor must be complete before its first review publication, or an explicitly owned new display handoff must replace that publication. Changing only JPEG's main descriptor at0x535048e8 cannot update an earlier descriptor copy. Copying a descriptor never acquires ownership of its Y/chroma allocation.

## Producer and original notification

`0x53517f0c` is the original BE-owner review helper. It chooses the current candidate recipe through original manager accessors (`0x53523438`, `0x5352355c`) and shooting-state checks. In its ordinary active-picture branch:

| Instruction | Proven behavior |
| --- | --- |
| `0x53517fb0..0x53517fb8` | Allocates a0x24-byte native notification payload through0x53522680. |
| `0x53517fc4/0x53517fc8` | Chooses native notification selector0x10 or0x1b depending on its original request classification. |
| `0x535180b4` | `r1 = sl + 0xb0`, where sl is the selected recipe. |
| `0x535180b8` | `r0 = payload + 4`. |
| `0x535180bc` | Calls original low-descriptor copier0x536a3d84. |
| `0x535180c0/0x535180c4` | Marks payload byte0=1 (active image). |
| `0x5351801c` | Calls original sender0x53522068 with payload in r2. |

Sender0x53522068 subtracts1 from its selector and indexes event table0x53d103e4. Selector0x10 therefore reads table entry0x53d10420=`0x71c81017`. It constructs/queues the native event through0x5382d064. The message's optional transport control is reference counted, but this is not a retain of the planes named by a copied low descriptor.

Original helper callers include0x5351d3c8 (BE event dispatch) and tailcall0x535204f8 (native callback dispatch). The latter switch is0x53520458, case9; the former receives original selector23 or31 according to the actual dispatch table. These are numeric backend selectors, not invented UI shutter labels.

### Earliest eligibility is earlier than JPEG in some actual planners

Original planner execution was repeated with the existing hash-locked `builds/gr3-800t-reverse/capture/planner-probe.py` from the primary checkout. Report: `/tmp/m10v-border-preview-planner.json`. All15 planners returned; existing restricted modes0/1/5/6/7/8/12 kept their established producer/JPEG/wait/cleanup checks.

In modes0/6, BackResize module5 is at index32, wait33, **kind4 at34**, JPEG module6 at35. Mode5 uses BackResize28, wait29, kind4 at30, JPEG31. Scheduler kind4 enters0x53515aa4 at0x5352012c. That helper can publish the recipe as BE-owner candidate (`owner+0x5a4` at0x53515c08), subject to its native state checks. This is not proof that display DMA starts at kind4, but it prevents assuming that the current pre-JPEG hook is the earliest review eligibility point. Other planner modes differ; do not extend the restricted topology without their own proof.

## Playback consumer, copies and display conversion

Playback sequence handler0x534a8290 reads native event at message+0, data pointer at message+4. It matches0x71c81017 at0x534a84e8..84f4 and routes through0x534a8a94..8a9c to named `DisplayQuickView` operation0x534a7ae0. The operation's debug string is0x53c5acd0.

1. `0x534a7af8` allocates a0x24-byte request. `0x534a7b44..0x534a7b50` copies active flag and low descriptor into that request with0x536a3d84. This is a second descriptor snapshot, not an alias to the recipe descriptor object.
2. `0x534a7bbc` calls0x534bbdf4, passing the request to the native QuickView/DirectView worker obtained from the existing Playback sequence. The outer operation frees its request at0x534a7bd8 after that call returns.
3. Worker0x534bbdf4 reads its persistent descriptor pointer at worker+0xc (`0x534bbe8c`). If absent, `0x534bbf20..0x534bbf84` allocates a0x20-byte low descriptor and stores it at worker+0xc. `0x534bbe98..0x534bbeb0` copies the incoming descriptor into this persistent object. Its plane addresses remain the borrowed source addresses.
4. `0x534bbeb8..0x534bbec8` keeps an independent source descriptor and builds the destination screen descriptor via0x534a9ad8. That function obtains original display-manager buffer backing, including0x536c62dc/0x536c761c, then selects screen geometry through0x534a961c. It does not make the LCD buffer the same object as a full-size JPEG plane.
5. `0x534bbed0..0x534bbedc` calls0x534bad8c with source and destination. That uses native display-image operations0x534c8d64 and fallback0x534c9094. The latter reads source width/height at+0x10/+0x12 and destination width/height to calculate a fitted rectangle (`0x534c90d8..0x534c9148`), then calls0x534ab6b8. This is evidence that display geometry is descriptor-driven; it is not an admission proof for every expanded capture size or orientation.
6. `0x534bbeec..0x534bbefc` marks the original worker state and invokes native display-manager0x534aa100. Its asynchronous source lifetime still requires the native graphics/driver completion contract.

### What the UI QuickView model/controller retain

Worker0x534bbcf8 computes geometry from the persistent descriptor and posts0x24480209 at0x534bbdbc. UI QuickView model event dispatcher0x532d551c routes that event to0x532d5408. The latter copies32 bytes from payload+4 into model+4..+0x23 (`0x532d544c..0x532d5464`) and posts UI event0x171 before forwarding the original payload. The inspected payload construction0x534bbd30..0x534bbd8c constructs rectangles from descriptor dimensions and origins. **These32 bytes are geometry, not a retained low-descriptor/plane owner.**

QuickView model is the static singleton at0x55063ddc, accessor0x5320bcdc. QuickView controller is a different native object, ControllerFactory+0xd8, exact vptr0x53b41380. Existing `m10v_view_deferred.*` extends that controller from0x184 to0x194 only to hold a16-byte event-generation token. Its generation/pending flags authenticate deferred native169 completion; they do not retain a recipe or image allocation. Its UI169/stop-reply ordering repair must not be repurposed as border ownership or a safe image-release signal.

## Original UI cleanup

Native stop operation0x534a7cc0 is named `StopDirectViewAndQuickView` (string0x53c5af7c), tailcalls0x534bb650. Depending on native active state, it requests deferred stop or reaches0x534bb5c4. Cleanup0x534bb5c4:

- calls0x534bafa8 →0x534cb560 to clear native display/zoom state;
- calls0x534a9744 for the native screen/display buffer path;
- frees **the worker+0xc descriptor object** at0x534bb5f0 and sets that pointer to0 at0x534bb5f8;
- posts original0x2448020b at0x534bb610 and clears native worker flags.

There is no source-plane free/refcount operation in0x536a3d84 or this descriptor-free site. The existing native source pool/recipe manager contract may keep original backing alive, but this investigation did not close that complete retain/release chain. In particular it does not prove that a recycled recipe or its appended border token survives UI display/zoom. Hooking only descriptor destruction is not proof that display hardware has stopped reading planes; the called graphics/driver functions and asynchronous stop path need a completion audit.

A separate expanded allocation would need an independently proved ownership transfer. The unchanged native-bank approach below avoids creating that new plane owner. No invented event or busy-flag clear is a release barrier.

## Follow-up: developed YUV is native public buffer ID5

Exact arithmetic matters: BEStillRecipe vptr is0x53d0fc90. Its **+0x9c** word is0x53d0fd2c →0x5350db3c (developed-YUV layout); its **+0xa0** word is0x53d0fd30 →0x53510fa0 (encoded output-control layout). Public **ID4 is encoded output storage**, not the developed image bank. Public **ID5 is the developed-YUV bank**. An early investigative message mixed these offsets; this section records the corrected raw-word contract.

| Native operation | Exact contract |
| --- | --- |
| Setter vptr+0x70 |0x5350d7e8; ID5 jump table0x5350d820 →0x5350d984. |
| ID5 set |0x5350d984 stores allocation base at recipe+0x304; nonzero invokes vptr+0x9c at0x5350d998..99c, i.e.0x5350db3c. That function binds R+0x70/+0x90/+0xb0/+0xd0/+0xf0 into the bank. |
| Getter vptr+0x74 |0x5350d458: `R + 4*(0xbc+id)`; ID5 reads R+0x304. |
| Requested-size vptr+0x80 |0x5350d47c: `R + 4*(0xd4+id)`; ID5 reads R+0x364. |
| Size production |0x53510cec calculates recipe sizes; the ID5 size is the3×stride×height path0x53510e5c, stored into the corresponding size table cell. Full native geometry/capacity admission is owned by the separate bank-layout investigation. |
| ID5 required flag |vptr+0x7c →0x5350d470 reads byte R+0x2d8+id, i.e.R+0x2dd. |

### Manager-owned banks survive ordinary recipe release

BE owner constructs its native buffer manager **M=owner+0x34** at0x53515530..53515540, by calling0x53520ea8. The constructor establishes:

- M+4=1 (baseline manager hold), M+8=2 bank slots;
- M+0xc / M+0x10 are bank allocation bases;
- M+0x14 / M+0x18 are occupied flags;
- additional fields support associated native buffers. Do not reuse them as border storage.

`0x5352125c` registers a recipe's requested buffers. For required ID5 it calls0x53520f28 then increments M+4 at0x535213f4..213fc. `0x53520f28` invokes the real size virtual and allocates each absent bank slot via0x536a27e8 using that requested size.

ID5 allocation helper0x535216d0 takes its special branch0x535217e4. It invokes0x53520fdc to choose an unoccupied bank; that helper decrements M+4 at0x53521068..2106c, marks the selected bank occupied at0x53521078 and returns its base. Original setter then binds that base to R+0x304 and lays out all five descriptors. The register/acquire pair therefore leaves the constructor's baseline1 in the tested ordinary transaction.

ID5 release in0x53521d14 uses table entry0x53521d68 →0x53521db4 →0x53521ea8 →0x535211f0. It does **not** use the generic ID4 pool-free branch.0x535211f0 compares the supplied allocation base to M+0xc/+0x10, clears the matching occupied flag, and calls0x53521084. The original release finally invokes setter(ID5,0), clearing R+0x304 while leaving any previously copied low descriptors stale.

In0x53521084, **the actual physical-free guard is the group counter**, read at0x535210d0: nonzero skips the free path. With normal baseline M+4=1, both native bank allocations remain owned by M even after the recipe handle is cleared. This is concrete native-manager retention, not a retain inferred from descriptor copying and not an image refcount added by QuickView.

If the counter is deliberately zero,0x535210f0..210fc only identifies the main-bank group for a log;0x535211d0 logs and returns to0x53521100, which physically frees the bank. That branch is **not** an early-return preservation branch. A negative control below executes this distinction.

### Review and zoom borrow the already-retained native bank

Review notification0x71c81017 carries the copied low descriptor and optional message-control ownership, not a new ID5 bank reference. Persistent Playback worker+0xc consequently keeps plane pointers into the existing manager-owned bank. Zoom operation0x534bcc38 reads that descriptor at0x534bcc70, copies it at0x534bcc80 and passes it into its mode-dependent native zoom dispatcher0x534bcac4. UI stop0x534bb5c4 frees the metadata descriptor, clears native screen/zoom state and posts its ordinary stop event; it does not introduce a per-view decrement of M+4 in the inspected chain.

This explains why a descriptor can remain useful after recipe recycling: the **bank**, not the recipe, remains natively cached. It does not justify retaining a recipe pointer, using another heap allocation without an owner, altering native occupied flags, or reusing the bank before the original capture/view transitions permit it. Cancellation, next-capture replacement and display DMA ordering should stay native. A new independent lifetime protocol is unnecessary only if all border pixels remain inside this exact existing ID5 bank and the original bank handle/counters remain untouched.

### Cache-capacity trap and assessment of the proposed zero-allocation plan

`0x53520f28` allocates a slot only when its pointer is0. It does **not** compare an existing allocation's capacity with a subsequent recipe's larger query. Increasing R+0x364 only when a user enables borders after ordinary shots cannot enlarge already-cached banks. Unconditionally reserving extra capacity while style is off would also contradict the approved off-state allocation constraint.

The coordinator's revised proposal keeps the **original native ID5 capacity/query unchanged**, lays out the padded source and relocated native preview regions entirely inside its existing unused capacity, and does so only for a frozen enabled style **before any YUV producer writes the image**. That proposal is compatible with the ownership evidence: the original R+0x304 must remain the true allocation base for bank matching/release, while low-descriptor plane pointers can refer to admitted subregions inside the same bank. No independent plane heap owner or new per-view refcount is needed. Descriptor metadata heap allocations in the native review path already exist and are unchanged.

The ownership result does not prove that every required plane/guard/preview interval fits, that B2R and BackResize consume the changed pitch correctly, or that border/secondary/EXIF geometry is complete. Those require the separate layout/consumer proofs. In particular, finalize R+0xb0 with **outer base, outer width/height, outer pitch/allocation and correct origins** before its first review copy. Leaving inner dimensions/origins while changing only its base will make native fit/zoom rectangles inconsistent. R+0xd0/+0xf0 and Setup6's copied R+0x110 still need corresponding content and geometry; shared bank ownership does not add missing borders to pre-resized thumbnails.

### Executed native-bank probe

Reproduce:

```sh
/Users/zhaoo/Desktop/code/zhaoo/m10v/.venv/bin/python scripts/probe_gr3_border_bank_ownership.py \
  --rtos /tmp/m10v-800t-analysis/rtos.bin \
  --output /tmp/m10v-border-bank-ownership.json
```

The hash-locked original ARM constructor, full registration helper, ID5 allocation helper/setter/layout and ID5 release path execute. Only pool accessor/alloc/free, unrelated logging and thumbnail-size helper are intercepted; no hardware or pixels are simulated. Five checks passed:

1. Native manager starts with baseline1 and two banks.
2. Registration increments2; acquisition returns the exact bank, marks occupied and balances back to1.
3. Ordinary release clears recipe backing/occupied state but makes **zero physical-free calls**; bank pointers persist in M.
4. A second synthetic query changing64MiB to128MiB still reuses the original two64MiB allocations with no resize, proving the capacity trap independently of any border arithmetic.
5. Deliberately forcing counter0 as a negative control causes the same original release path to free both banks and clear both cached pointers. This is not a claimed native UI counter transition.

The synthetic capacity values test reuse/ownership only. They are not camera capacity recommendations. The probe creates no firmware and does not alter native pool/view state on a device.

## JPEG and embedded preview/thumbnail channels

Established Setup6 at0x5350ea50 first copies R+0x70 to **R+0x110**, then binds:

| Codec input | Low descriptor | Output control |
| --- | --- | --- |
| src0 | R+0xb0 | R+0x130 |
| src1 | R+0xd0 | R+0x148 |
| src2 | R+0xf0 | R+0x160 |
| src3 | R+0x110 | R+0x178 |

BackResize config B=R+0x904 binds source R+0x70, main R+0xb0 and secondary outputs R+0xd0/R+0xf0. Its synchronized hardware path waits0x534fec24 and clears completion0x534fec30;0x534ff44c invokes that path before returning to generic owner completion. Therefore these secondaries already exist before JPEG hook0x535048e8.

At codec service opcode3, main src0 is encoded at0x536643ac; src3 at0x5366438c; src1 at0x53664428; src2 at0x53664048. Enable bytes+0x21/+0x22 gate src1/src2 separately; the capture caller sets both1. Setup6's descriptor objects and the pre-encode source/output pointer array are precise, but **this codec evidence alone does not name src1 vs src2 as EXIF IFD thumbnail vs MakerNote/display preview**. The exact output-control-to-container writer mapping remains to be proved. Observed user files contain both160×120 and720×480 preview entities; their existence does not identify which codec channel writes each container entry.

Native allocation0x5350db3c computes secondary capacities from recipe preview geometry and helper0x536a2f10; the existing allocation probe stubs that helper to160×120, so its output is not evidence that all shooting configurations use fixed thumbnail dimensions. Do not hardcode the expanded outer image back to3:2 or enlarge low descriptors without matching real allocations and metadata.

For borders, every encoded secondary must come from the composed geometry or receive an independently valid hardware border/resize job. Updating only src0 misses the already-resized secondary buffers. Updating R+0x70 after Setup6 also misses the copied R+0x110 descriptor. Preserve CFA and its metadata. Genuine aliases can share backing only after interval/format/stride validation; separate descriptor addresses do not establish independent backing.

## Minimal viable integration sequence, conditional on ownership proof

1. Freeze style at real task ingress. Complete the expanded main composition at the BackResize completed-worker boundary **before original owner completion and downstream kind4 eligibility**. Keep original callback/scheduler serialization. Finalize all low-descriptor fields only after hardware completion. Do not treat JPEG hook as the universal earliest publication boundary.
2. At the same transaction, produce or rebind the encoded secondary channels and extra preview descriptor coherently, with proper per-channel capacity, geometry, orientation, failure and RAW protection. An earlier source-stage alternative is possible only if stock BackResize crop/output planning is explicitly adapted; simply widening R+0x70 can be cropped back or overflow old buffers.
3. Preserve the original notification0x71c81017 and its first copy site0x535180bc. Before that copy, authenticate the selected recipe and provide the already-complete expanded main descriptor, backed by an owner whose lifetime is valid beyond recipe recycling. Follow the existing display buffer acquisition/fitting/publish calls rather than directly editing a QuickView UI bitmap.
4. Keep any new independent allocation alive for retained worker+0xc, screen conversion, direct review and zoom; its release protocol remains unproved. Prefer the admitted unchanged-ID5-bank plan above, which inherits original native-manager retention and original next-capture/stop ordering without introducing a new allocation owner. Later JPEG completion/Store return/real169 do not substitute for native bank ownership or hardware completion.

## Executed evidence and limits

Original ARM copy sequence was executed in Unicorn from the exact hash-checked RTOS with a6320×4640 low descriptor, stride6336, addressMode2 and dirty padding. No image hardware calls were intercepted because the executed fragments only copy metadata:

- `0x535180b4..0x535180c8`: recipe+b0 → payload+4, active flag1.
- `0x534a7b44..0x534a7b54`: payload → independent heap request.
- `0x534bbe98..0x534bbeb4`: request → persistent worker+0xc descriptor.

All meaningful descriptor fields were preserved. Changing the original recipe descriptor after the first copy, and changing the temporary request after the final copy, left retained copies unchanged. The plane addresses were not dereferenced or retained by a reference-counting operation. This proves copy timing/staleness and scalar ABI, not6320×4640 display acceptance, physical buffer lifetime, orientation, JPEG/EXIF consistency or device speed.

Only this research document and its standalone original-ARM probe were added/updated for this ownership investigation. No production integration or hardware release/cancel path was activated or claimed complete.
