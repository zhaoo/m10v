# GR III Polaroid 3:2 center-crop recovery r2

Status: USER_VALIDATED. User authorizes main/GitHub/Baota release.
GitHub main was fetched again and remains
`4a89fd5d1fd3405c0f5f1fb1655709d4fe41e221`.
This candidate contains the r1 LED fix and the minimal border handoff repair.

## Physical r1 evidence

The user confirms that r1 fixes persistent LED blinking after film selection.
This accepts the LED behavior only; the full r1 build was not accepted.

The supplied CP/IO pages are CRC-valid with build ID `4feade09`, no rejected
pages. Saved JPEG 4403 is 6000x4000 with a full-width 160px white bottom strip.
Module10 returned with a complete 6320x4640 canvas, frozen shot `0x42524461`.
Before and after JPEG recovery, all three large descriptors instead reported
6000x4000, Y `0x624c71e0`, C `0x6429a7e0`, stride6336, rows4640.
Bank `0x6211a940`, capacity74907648. Stage4 reason264 (`0x100 | 8`)
identifies rejection of the Y provenance check. Previews already used the
bordered ratio: 652x480 and158x116.

For the authenticated bank the full canvas Y is `0x622d8140`. Native center
cropping6320x4640 to6000x4000 uses X160/Y320, yielding exactly the logged Y.
The Polaroid photograph inset is X160/Y160. The native centered view therefore
removes the top/side borders but retains exactly160 rows of the bottom border,
matching both the uploaded JPEG and the reported playback symptom.

## Repair and preserved boundaries

The COMPLETE-phase JPEG handoff now accepts either the original authenticated
inner Y or the exact center-crop Y derived from the same frozen bank/layout.
Both source and main Y must match. No arbitrary in-bank pointer is accepted.
Existing full-dimension, format, tag, frozen-stage and canvas-bound checks
remain. The original full canvas is reconstructed from the proven bank, not
from the newly admitted crop pointer. Source/main/extra descriptors are restored
together; previously generated full-canvas previews are retained.

There is no new pixel loop, IIP job, frame allocation, filesystem transaction,
storage ABI, native ISP/RAW lifecycle change or persistent settings change.
The LED cache fix, Half pair separator, all other border paths and features
continue from r1. GR IIIx shares the runtime and is covered by isolated ARM
metadata checks; only the requested GR III 2.10 firmware is delivered.

## Candidate and verification

Output directory: `builds/gr3-led-polaroid-r2-20261031`.
Build through the existing export chain:

```sh
node scripts/export_gr3_m10v_native.mjs --debug --border --with-hdf --universal-halation builds/gr3-led-polaroid-r2-20261031
```

BIN SHA-256:
`047a9e1efa2c4c552a938d6773f28cb8ca94172d605fc53306e989ed2033b42a`.
Debug build ID: `c2a092eb`. Packaging readback verifies268 hooks.

The new centered-crop regression fails on r1 for all four supported capture
orientations. With the fix it restores exact full-canvas metadata, without
additional allocation/resize/callbacks. An eight-pixel displaced pointer still
fails closed. A second regression uses literal metadata from JPEG4403 and
checks literal output Y/C and6320x4640 geometry on both GR III and IIIx ARM.
The final-BIN test independently repeats the physical metadata case against
the delivered runtime and checks no cache/allocator/storage work.

25 final-BIN pipeline/metadata checks and60 border ARM/build/canvas checks pass.
Full Node suite:479 tests,425 pass,36 fail,18 skip; all36 failing names match
r1 and the pristine-main comparison, with no new failing names. Full results
are recorded in the generated candidate validation report. Metadata fixtures
do not prove real pixel/DMA completion; the independent current ISP pipeline
tests retain the genuine producer/Still Make/encoder checks.

## Device gate

First test one landscape3:2 Polaroid capture, immediate playback and album/zoom.
The expected saved canvas is6320x4640 around the6000x4000 photograph. Return
the original JPEG and CP/IO logs for this shot before further captures overwrite
the bounded ring. Then optionally test portrait, square and135 borders.
The original test instructions above record the requested scope. The user has
now explicitly confirmed both LED and Polaroid fixes. They subsequently
retracted the suspected Half crop failure as originally working and requested
merging these fixes to GitHub main and publishing to Baota/GitHub.
Acceptance binds the unchanged r2 BIN SHA and build ID recorded above. The
Half diagnostic repack contained the exact same firmware and no Half changes.
Preserve existing card settings; recovery remains the user's previously
accepted firmware. This approval does not expand GR IIIx/IV device evidence.
