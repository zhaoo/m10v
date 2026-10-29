# Border JPEG metadata and capture orientation contract

Read-only investigation, 2026-10-27. Original GR III 2.10 RTOS SHA256 `8a4eafcad2716e0b21e9909264e1242e534f0e39e05cba82a53546ceb4070b67`, mapped at `0x53000000`. No firmware activation, physical-camera evidence, or GR IIIx address-equivalence claim.

## Pixel dimensions have an output-frame source

`StoreImageProcess` normal save handler `0x5350bfb0` calls native frame-info creator `0x5350afec` for each output (calls at `0x5350c21c`, `0x5350c238`, `0x5350c250`). Mode 0 chooses config+0x40 descriptor and config+0x50 encoded-result object at `0x5350b1a8..b1ac`. The store setup binds those fields to `R+0xb0` and `R+0x130` at `0x5350e970`, `0x5350e980`, `0x5350e9e4`, `0x5350e9f0`; config base is `R+0xb4c`.

The creator reads descriptor width/height with `ldrh` from +0x10/+0x12 at `0x5350b078`, `0x5350b080`, and stores **32-bit width/height at frame-info+0/+4** at `0x5350b0a0..b0a8`. It separately records crop/origin, bit depth, encoded length and backing. Mode 1 selects config+0x44/+0x54 (`R+d0`/`R+148`); mode 2 selects +0x48/+0x58 (`R+f0`/`R+160`); mode 3 selects +0x4c/+0x5c (`R+110`/`R+178`). These are independently dimensioned output infos.

At the lower file writer, `WriteStillFile` `0x534eb8b4` takes the main frame-info as original **r1**. It constructs metadata registry P with `0x535fc234`, then calls `0x535fc2e0(P,2,original_r1)` at `0x534eba10`. Type 1 is original r2; type 0 is original r3. SI is passed separately into `0x535fc2d0` at `0x534eba00`. Registry getter `0x535fc308` resolves slot type2 at `P+4*(4*P[0]+8)`. Setter refresh `0x535ff8ec` stores that pointer at `ExifJpegExifEntryDataSetter+0x24`.

Actual main EXIF setter `0x535ff9dc` handles:

| Tag | Native source | Write |
| --- | --- | --- |
| 0xa002 PixelXDimension | `*(uint32_t *)(setter+24)` -> pointee+0 | `0x535ffa34..ffa40` -> `0x535d02e0` |
| 0xa003 PixelYDimension | same pointee+4 | `0x535ffa68..ffa74` -> `0x535d02e0` |

`0x535d02e0` writes a 32-bit LONG into entry inline storage +0xc, or entry+0x10 external data if nonnull. It does not consult sensor geometry or a live size-setting enum.

The intervening file stack statically passes width object pointers: `0x534e0e94` extracts packet+4 into sl; passes it as r1 to `0x534e8794` at `0x534e0f04`; that function saves original r1 and reloads it at `0x534e8810` before calling WriteStillFile at `0x534e8828`. This is the separate event-based writer path; the actual capture Store path is established in the next section. Do not assume the two paths share a call edge.

## Actual capture Store path is now closed

The normal capture group **does not need to pass through WriteStillFile**. That named writer belongs to a separate path: event70c81011 is packed by534d679c and its directly found caller534db808. The normal Store producer passes group G at5350c3f0 into the request sent at5350c438. Native service singleton53693f28 creates worker vptr53d591c8; its request-interface virtual+10 thunk53698ea0 reaches53698914. That dispatcher selects request+0xc opcode00800001 at53698954 and takes53698adc. Request+8 is G.

Normal flow53698cc4 calls5369701c, whose loop uses record D=G+0x14+0x5cc*streamIndex (first D=G+14). D+4=G+18 is the main frame info produced by5350afec above. At5369728c it calls53695408(worker,D,streamIndex). That routine binds actual embedded registry P=D+3f0 (first P=G+404):

| Registry slot | Exact normal binding | Native call |
| --- | --- | --- |
| type2 main EXIF dimensions | D+4, therefore G+18 |53695474..53695488|
| type1 MakerNote preview | D+50 |53695490..53695498|
| type0 thumbnail | D+9c |5369549c..536954a8|
| type3 additional frame | D+e8 |536954ac..536954b8|

At53697300,535fc2d0 additionally registers SI loaded from D+134.5369535c builds a writer request:53598cec installs D+478 as image-info,53598cf4 installs P=D+3f0,53598cfc installs D,53598d04 installs completion;53599510 submits that actual request. Thus the **normal capture main metadata slot2 is proven to point directly at the main frame generated from R+b0**. The original ARM probe now executes53695408 and actualmainEXIFsetter on this exact object shape and gets6320x4640. Native output types7/8 intentionally rebind slot2 to D+9c/D+50 at53695560/53695574; do not override those preview/export variants.

No separate EXIF size hook is needed for ordinary still capture when R+b0 is finalized before5350afec. Keep native frame registry setup and channel selection unchanged. The remaining file evidence limit is full asynchronous container assembly and physical-camera output, not uncertainty about the normal Store registry dimension pointer.

## RAW remains a different geometry contract

RAW frame-info creator `0x5350b238` reads config+0x30, follows +0x88, and copies its sensor/crop geometry at `0x5350b254..b2c0`. It does not use the main YUV descriptor. Existing `m10v_aspect_dng.c` consumes image+0x7c geometry, +0x84 properties and native fallback `0x540b7308` to produce DefaultCrop metadata. None of these fields should be enlarged to canvas size. Keep CFA storage, CFA dimensions, ActiveArea/default crop and RAW stride untouched.

The minimal output-only integration is to finalize `R+b0` width/height before the original Store frame-info creator (and before the review copy as separately documented). That gives the native output metadata creator the same canvas as the JPEG encoder. Do not change the shared SI image-size setting or sensor geometry to obtain JPEG EXIF dimensions. The actual normal Store registry linkage above now removes the stale-clone concern. No extra dimension override is implemented or required by this evidence.

## MakerNote preview and unknown capture-size label

Pentax MakerNote tag 0x0002 is PreviewImageSize, a pair of SHORTs, per [ExifTool's primary Pentax tag definitions](https://raw.githubusercontent.com/exiftool/exiftool/master/lib/Image/ExifTool/Pentax.pm). Native dispatch `0x53606738`, tag2 target `0x536083c0`, passes this+0x10 to helper `0x535c7590`; the helper reads frame-info+0 and +4 and writes two SHORTs. MakerNote setter refresh `0x53603f18` obtains this+0x10 from **registry type1**, separately from main type2 at this+0xc. Tag3 preview length reads type1 frame+28 via `0x535c75d0`; tag4 preview start reads type1 frame+38 via `0x535c75e8`. Thus the MakerNote preview metadata must describe that preview channel, not the main canvas by fiat.

No separately named native “capture image size MakerNote” enum is identified in this investigation. Tag9 PentaxImageSize from generic Pentax documentation is **not handled** by this GR III setter: its jump table routes tag9 directly to return0 at `0x53608400`. Existing original GR III samples locally inspected list PreviewImageSize720x480 and FaceImageSize6000x4000, without PentaxImageSize. FaceImageSize describes face-coordinate space, not an automatic main-output dimension tag. Its native source/coordinate adjustment is not proved here. Do not invent a 6320x4640 camera size enum, overwrite unrelated MakerNote blocks, or claim all size-bearing MakerNotes have been reconciled.

## True saved orientation

Common TIFF tag0x0112 dispatch is `0x535f79f0` -> `0x535f7d6c` -> **`0x535f673c`**. Refresh `0x535f6368` obtains the capture SI from registry getter `0x535fc2f8`; sets this+8=SI and this+14=SI+0xc8 (`0x535f63d0..63d4`). The orientation helper implements:

1. If `*(uint32_t *)(*(uint32_t *)(registry+4)+0x144)` equals2 or3, write EXIF1.
2. If SI+0x71e03 byte is nonzero, use SI+0x71e04 byte.
3. Otherwise use **SI+0xc8 byte**.
4. Internal1 -> EXIF8, internal2 -> EXIF3, internal3 -> EXIF6. Other values -> EXIF1. Tables `0x53d30188` and `0x53d30190` contain (8,3,6).

Store setup reads recipe+0x44c8 at `0x5350e954` and writes it to config+34 (`R+b80`) at `0x5350e9b0`. This is a saved capture SI route, not proof that a live orientation global is synchronized to that shot. A property setter at `0x53552f58` follows its owner+4, updates +0xc8 and +0x8e8, and notifies via `0x5355198c`; its device producer and exact relation to capture freeze timing remain unproved. There are other +c8 writes in RTOS, many belong to unrelated structures and must not be treated as SI evidence.

For a border decision before first YUV production, use the saved recipe SI at the already integrated5351ea9c producer ingress; the initialization copy timing is established below. Preserve native EXIF orientation; dimensions remain stored raster dimensions and are not swapped merely because EXIF is6/8. The initialization proof below establishes the saved SI availability at the existing producer hook. Sensor-to-property event timing and physical direction labels remain separate device evidence.

## Reproducible bounded original ARM probe

`scripts/probe_gr3_border_exif.py` runs original instructions from the hash-locked RTOS. Example:

```
/Users/zhaoo/Desktop/code/zhaoo/m10v/.venv/bin/python scripts/probe_gr3_border_exif.py --rtos /tmp/m10v-800t-analysis/rtos.bin --output /tmp/m10v-border-exif.json
```

Eight checks pass: descriptor6320x4640 -> mode0 frame info; actual metadata registry/refresh/main EXIF setters ->6320x4640; actual Store record registry ->EXIF; original complete SI freeze/source independence; independent MakerNote preview720x480; SI orientation0..4 ->1,8,3,6,1; SI override; metadata modes2/3 forcednormal. Logging boundary is stubbed. Synthetic object state is supplied. This does not execute the full scheduler, TIFF/JPEG container assembly, hardware encoder, DMA, GR IIIx firmware, or a physical camera, and makes no claim that a complete bordered JPEG has matching SOF/EXIF tags.

## Orientation freeze timing and usable ingress

Recipe initialization53510800 accepts originalr2 as optional saved source SI. If nonnull,53510820 loads destination from R+44c8;53510824/2c loads length0x74270;53510830 calls5313fd80(destination,source,0x74270). The return/rejoin53510834 is therefore **after the full SI snapshot including+c8 and+71e03/+71e04**, before recipe-specific configuration53510468, native request initialization535134fc at5351084c, geometry setup via virtual+90/+98 and any module submission. SourceSI arrives from BEowner+9a8 in ordinary call5351b568 (loaded5351b55c), and5351cfac (loaded5351cfa4). The notification parser53516b40 extracts incomingpacket+14 at53516b70 and publishes it BEowner+9a8 at53516bac; another parser53516bfc uses packet+10. Do not replace either incoming shot SI with current UI Property.

The existing recipe producer hook5351ea9c runs after initialization and before enqueue of that recipe's processing packet; source recipe is originalr1. It can read the already frozen `*(R+44c8)+c8` with the same recipe/SI RAM validation used for tone. It must also honor the saved SI override+71e03/+71e04 when matching final EXIF. For normal capture metadata modes0/1, internal0=>EXIF1,1=>8,2=>3,3=>6,other=>1. Read SI pointer and selected orientation twice before publishing the border snapshot to detect mutation; no live global/I/O/allocation is needed.

For a strictly earlier geometry-layout hook,53510834 is the precise postcopy site with r4=recipe, r5=recipekind and r6=recipe+4000. This ingress is before registration/acquisition of the developed-YUV banks: caller5351b56c..574 follows initialization with5352125c. Its displaced instruction is `mov r0,r4`. It is useful for freezing orientation, but must not replace existing border style authentication or perform allocations. Null originalr2 skips the SI copy; such reprocessing paths require validated existing saved SI and a proven supported recipe kind rather than assuming a new exposure. The existing first-submit5351ea9c is the preferred already-integrated snapshot point for ordinary captures; no additional early hook is required solely to read orientation.

The probe executes53510800 through53510834, including original NEON memcpy5313fd80 over0x74270 bytes; compares every destination byte, then changes source orientation and override, proving the copied recipe SI remains independent. It subsequently executes the real TIFF orientation writer against that copied SI and retains EXIF6. No image pixels are copied by this research probe; the copied original structure is native shooting metadata.
