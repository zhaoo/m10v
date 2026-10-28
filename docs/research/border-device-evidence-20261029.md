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
