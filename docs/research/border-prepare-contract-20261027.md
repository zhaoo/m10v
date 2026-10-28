# Inactive StillMake border prepare adapter

`native/gr3/m10v_border_prepare.c/.h` provides
`int m10v_border_prepare(uint32_t module,uint32_t config)` without installing a
hook or changing any builder registry. It is intended immediately before the
original R2Y submit at53501f98, after native helper/output binding setup, under
exclusive current-recipe ownership. It must precede the first YUV output write.
The three native stripe requests may call it repeatedly while phase is FROZEN.

Return1 means the metadata plan was committed,0 means an owned frozen OFF shot
was encountered, and-1 means rejection. OFF reads no module/image descriptor and
does not call the bank planner. Rejection writes no recipe/module metadata.
The successful multiword commit requires the caller's exclusive owner contract;
it is not an atomic publication to concurrent native readers.

## Admission and commit

The adapter derives recipe=config-96c, then validates the existing owned shot
API's vtable/extension/frozen-style identity, frozen orientation and FROZEN phase.
Config+30 and module+9ba8 must point to recipe+1a8; config+34 must equal the owned
recipe's R44c8 settings pointer; config+38 must match R5c. Config bank+10/+14
must equal R304/R364. Config+49 must be0.

Both original B2R params+9904 and R2Y params+9938 must have flags
`[1,1,1,1,0,0,0,0]`. Four pointers module+9914/18/1c/20 must reference format8
descriptors with all three memory-plane pointers0. R2Y's byte1 selects the live
stream input and byte3 enables the output path. The current R2Y channel descriptor
module+9944 must have byte8=4 and its crop-enable byte+a must equal nonzero
status+d0, as written by original53501910.

The adapter snapshots the five low descriptors R70..Rf0, config source planes,
inline output descriptor+994c, three stripe offsets status+102/104/106, widths
status+ee/f0/f2, and ROI X status+da/dc/de. Config+18/+1c must exactly match R70
planes. Inline Y/C must use the same one of those three byte-column offsets;
no row/stride conversion or ROI addition is applied. Inline format1, third
plane0, W/H, cacheRows and ROI must match the corresponding native metadata.
Inline H is status+d8 and ROI Y is status+d4. The source visible W/H and RAW
status are unchanged.

The inline cache-row halfword at module+0x9962 comes from status+0xac in
original instructions 0x535019e4..0x535019ec. It need not equal the visible
source height. GR III camera logs from build 1c71d979 showed border style2
saved and available at capture, then BORD stage2 reason25: the previous
adapter compared this field with visible height and rejected the frame before
border hardware work. The adapter now compares the two stock-owned fields and
rechecks status+0xac before committing relocated metadata. Expanded-bank and
conservative write-extent checks remain. Camera pixel and timing acceptance
of this candidate remains pending.

The existing pure bank planner validates and computes all five relocated low
descriptors within the original bank5 capacity. Before committing, prepare
checks every stripe's configured write width against the original common pitch,
then bounds the larger conservative `(ROI+W+1, ROI+H+1)` extent against the new
row capacity and reserved plane guards. This extra bound does not reinterpret
ROI as a destination memory displacement. It reserves room even for an end
coordinate interpretation while preserving the original native programming.
Native H and the larger vertical bound must remain within source H+144 rows.
All sampled descriptors, bank/context identity, flags, crop geometry and frozen
shot state are rechecked before the first write.

Success commits only the five planned low descriptors, config+18/+1c and inline
Y/C planes plus the inline byte pitch+9960. All other inline fields, including
native halo ROI/W/H/cacheRows, stay byte-identical. Common RAW status/R252,
bank identity/capacity, image storage, RAW owner token, filesystem and scheduler
state are untouched.

## Native halo evidence

The original geometry writer and StillMake bindings supply these native values:

| Stripe | Byte column | ROI X | Configured W | ROI Y | Configured H fixture |
| --- | ---: | ---: | ---: | ---: | ---: |
|0|0|68|1972|40|4012|
|1|1960|12|1996|40|4012|
|2|3944|12|2068|40|4012|

These are producer halo values, distinct from the source low descriptor's
visible6000x4000. The last configured row end is6012, which fits a native6016
or6144 pitch. The new full canvas source inner column160 plus6012 is6172, below
6336. The original source/main144-row relation and tail guards are preserved by
the separately reviewed bank planner; BackResize later performs its native
source/main aliasing and crop.

`probe_native_halo` in `scripts/border_yuv_bank_contract.py` executes actual
53501910, actual5366dc90 and actual537cb4e8/register setters for both pinned ROMs.
The three old6144/new6336 runs differ across the complete512-byte register
fixture **only at stride registers140/144**. Original crop registers178/17c and
all other fields stay identical. Packer5366de80..de9c transfers ROI/W/H to native
+60/+64/+68/+6c; original setters537dd520..537dd59c transfer those unchanged to
178/17c. Planes are copied independently from the inline descriptor and remain
base+column. ROM dump text identifies the write trimming group as TRM0H/TRM0V.
This is original instruction/register preparation evidence, not an execution or
independent hardware specification of physical DMA writes.

## Verification

Tests were written and observed failing before implementation. Run:

```sh
/Users/zhaoo/Desktop/code/zhaoo/m10v/.venv/bin/python -m unittest tests.test_gr3_border_prepare -v
/Users/zhaoo/Desktop/code/zhaoo/m10v/.venv/bin/python -m unittest discover -s tests -p test_border_yuv_bank_contract.py -v
```

The prepare tests execute the same C source in a host executable, and scalar
ARM code linked with the real shot and bank modules. Darwin host tests use an
x86_64 executable under Rosetta with a bounded PAGEZERO and no PIE so firmware
metadata addresses below4GiB can be mapped safely in that isolated process.
Only metadata RAM is mapped; all photo-plane addresses remain unmapped.

ARM tests run against both hash-pinned original ROMs. Besides a bounded synthetic
zero-ROI fixture, they execute real53501910 and original StillMake plane/ROI
binding fragments, call prepare for all three native halo stripes, then run the
real original R2Y packer and verify the new pitch and unchanged crop/plane offsets.
They also inject a changed bank capacity after the pure planner returns and
verify prepare rejects without partial descriptor/inline mutation. Forbidden
snapshot/allocator/wait/submit/filesystem entry points fail the ARM test.

Host tests cover native halo preservation, native pitch restoration between
three idempotent requests, OFF short-circuiting, postprocessing-phase rejection,
owner/context/flag/plane/geometry refusal, insufficient capacity, and unsafe
post-plan ROI extents. No camera pixels, physical completion, image quality,
first Review or JPEG integration result is claimed. No runtime hook is installed.
