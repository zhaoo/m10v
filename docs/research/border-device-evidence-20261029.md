# Border camera evidence, 2026-10-29

GR III 2.10 diagnostic build `305e6301` was physically tested with the film
style. User supplied CRC-valid `M10VCP0/1.BIN`, `M10VIO0/1.BIN`, and original
JPEG files `00004347.JPG` (6000x4000) and `00004348.JPG` (XPan 6000x2208).
Neither saved JPEG contains the outward border. This is a file result, not just
the camera playback display.

For the ordinary frame, module 21 BackResize entered with main descriptor
6000x4000 and returned with **6480x4480** (`0x11801950`). Module 12 entered
and returned with the same expanded descriptor. At JPEG capture owner event
193, the same recipe's shot word had style2, phase3 Complete, but `R+c0` was
back to **6000x4000** (`0x0fa01770`). The JPEG file confirms stock SOF size.
The overwrite lies after module12 return and before owner event193. Module10
is scheduled there but its ordinary trace record was dropped by the 27-record
limit; the exact writer is not yet proved.

For XPan, module21 entered and returned with main descriptor6000x4000;
the shot word at event193 had style2, phase5 FailedBeforeLibrary, and `R+c0`
was 6000x2208 (`0x08a01770`). The saved JPEG uses6000x2208. The current
`m10v_border_runtime_after_resize` transitions phase Prepared->FailedBeforeLibrary
on negative returns -3..-8 without recording a reason. Thus the stage-1/2
`BORD` trace reservation did not identify this XPan refusal.

The next diagnostic records after-resize rejection stage3, module10's return
descriptor in the reserved trace slot, and source/extra descriptor sizes plus
source/main Y pointers at the safe event193 flush. All are metadata-only.
They establish the exact handoff boundary before any repair to saved JPEG or
XPan is attempted. This build remains a diagnostic, not a working border JPEG.

## GR III debug3 readback and late handoff candidate

The next CRC-valid `M10VCP0/1.BIN` and `M10VIO0/1.BIN` use build ID
`5a362393`. Files `00004350.JPG` and `00004351.JPG` are again 6000x4000
and 6000x2208 respectively, without border pixels. Ordinary module10 returned
with **6480x4480** and frozen film phase Complete. The event193 JPEG owner
then saw both source/main as 6000x4000, with source Y equal to main Y.
This narrows the overwrite to after module10's handler return and before the
JPEG owner entry. XPan's BackResize exited at 6000x4000 and logged stage3,
reason6; by event193 the native owner had cropped both source/main to
6000x2208, with frozen phase FailedBeforeLibrary. The residual bridge returned
stock-tone refusal -4. Physical JPEG SOF dimensions corroborate those paths.

The new candidate calls the existing residual bridge first at the owned JPEG
handoff. For phase Complete it restores the previously composed full canvas
only when the native bank's exact Y/C provenance, frozen style, full-frame
dimensions and bounded canvas layout all match. For a native crop that failed
the early reason6 check, it admits only a crop within the originally prepared
bank, performs border Fill plus two preview Resize jobs through the same
guarded IIP workers, then publishes expanded descriptors. The crop can begin
at any even X; at most six pixels of the outward margin are shifted to align
the IIP canvas base. No CPU photo-pixel loop or second full-frame bank was
introduced. The GR III and GR IIIx ARM tests exercise full frame, XPan and
an even but non-eight-aligned 6x7-like crop. These are simulated control-flow
checks, not a physical pixel or silicon teardown acceptance. Exact 6x7 camera
dimensions and all real orientation/sequence modes still require camera tests.

## GR III aspect and playback report

The next camera upload uses build ID `4ee18501` (CRC-valid CP/IO pages).
`00004352.JPG` is 6480x4480 film and `00004353.JPG` is 4480x4480 film:
both contain the 135 border. The second shot's stage4 reason2 confirms the
late IIP crop path ran. `00004354.JPG` is a 6000x4000 Polaroid shot with a
white lower strip but without the saved outward canvas. Its module10 returned
6320x4640 and frozen phase Complete; JPEG owner saw 6000x4000. No stage4
success marker was emitted, so the phase-Complete descriptor recovery rejected
the owner-restored metadata before encoding. The next adapter reconstructs C,
stride and auxiliary words from the already authenticated native bank and
frozen shot when both Y addresses still match the prepared inner view; it
records stage4 reason10/11 if that tighter provenance check still fails.

The previous test package explicitly omitted the optional aspect component.
Its menu therefore lacked XPan and 6x7. The aspect component's menu sequence
also omitted native ID2 16:9 even though that stock identity remains present.
The next build includes the checked aspect component for both models and lists
3:2, 1:1, 4:3, 16:9, XPan and 6x7. This restores menu availability; real
camera capture under all restored modes is still a test gate.

The user reports size pulsing only while browsing bordered saved photos in the
camera album. The three files contain embedded thumbnail/intermediate/main
JPEG dimensions of 160x110 / 694x480 / 6480x4480, 120x120 / 480x480 /
4480x4480, and 160x116 / 652x480 / 6000x4000. The Polaroid file therefore
has a major preview/main aspect disagreement. The full-frame restoration above
addresses that. The small film thumbnail ratio is also visibly rounded; the
new bounded preview fitter selects a closer even ratio within its existing
allocation. Its physical album transition still needs camera verification.
