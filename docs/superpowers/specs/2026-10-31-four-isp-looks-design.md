# Four additional ISP looks

Status: user approved for implementation on 2026-10-31; source audit continues. Base: `a901016cd4f1ebfe917dbe195d2c5711af9309a1`.

## Intent and accepted requirements

Add four visible looks without altering existing identities or settings:

| Stable ID | Name | Existing directory group |
| --- | --- | --- |
| 318 | 2383 | ECN2 |
| 319 | Classic Negative | 影像 |
| 320 | Classic Chrome | 影像 |
| 321 | LomoChrome Purple | 创意 |

The user's “ENC2” refers to the existing ECN2 group. Place 2383 there as requested while documenting that it is a print stock, not an ECN-2 camera negative. Append inside each group and preserve all previous IDs, resource mappings, ten active slots, per-film settings, SD compatibility, borders, Half, HDF, RAW boundaries, and existing effects.

The user explicitly accepts ISP approximation with disclosed error and physical-camera acceptance. This does not authorize a claim of exact film/camera reproduction. No CPU color processing is permitted for these four looks.

## Approaches

1. Retain and execute original 3D LUTs on the CPU: rejected by the user's performance requirement.
2. Quantize traceable source transforms offline into existing native ISP matrices, multiaxis sectors, and curves: selected by the user's clarification. Keep unmodified reference identity, normalization assumptions, quantized output, and error evidence distinct.
3. Author visually similar filters without traceable numerical references: insufficient where manufacturer or licensed community numerical data are available; avoid as a replacement for the named source.

## Source selection

- Classic Negative and Classic Chrome: prefer Fujifilm's GFX ETERNA 55 v1.10 official archive. Its named F-Log2 LUTs are verified present. Record source/archive hashes, LUT version, F-Gamut input and BT.709 output, and official gamma documentation. Normalize the model input explicitly; do not apply an F-Log2 LUT directly to display RGB. Verify usage terms before retaining or distributing source assets; use a fetch-and-verify build input if redistribution is not established.
- 2383: Kodak H-1-2383 technical data plus the existing MIT Spectral Film LUT digitization, or the existing MIT G'MIC-derived named 2383 LUT after provenance/input-domain verification. Freeze one declared print/display adaptation rather than silently substituting a camera-negative look or a Log LUT.
- LomoChrome Purple: verify a named, licensed community numerical source against Lomography's official Film Guide. If unavailable, document the exact limitations of official-guide digitization; do not silently replace it with a freehand channel swap. Source identity must be resolved before enabling this entry.

## Runtime and model scope

Use the existing GR III 2.10 native pipeline: real task producer → immutable per-shot settings → Still Make ISP parameters → recipe/SI/generation-bound completion → JPEG admission. The CPU may prepare bounded ISP parameters; it must not transform image pixels. No new CPU LUT, full-image buffer, per-shot source-file parsing, or fallback color renderer for these IDs.

Add profiles and supported-ID handling to the existing native path, include menu/artwork/catalog/SD identity consumers, and keep web previews tied to the quantized ISP output. Other camera models must reject the new IDs until their own native ISP path is independently verified. Do not advertise support by reusing the GR III addresses.

## Evidence and acceptance

- Preserve source versions, licenses, hashes, normalization formulas, fitting seeds and solver settings.
- Fit against original floating-point source transforms before display-table downsampling. Report quantized ISP versus source ΔE00 median/P95/max, RGB error, neutral ramps, skin patches, saturated colors and sector seams on independent samples. Report web-table interpolation separately.
- Run catalog/state/SD migrations, profile bounds/readback, native build and final BIN audit, plus real producer-to-Still-to-JPEG tests with image pixels unmapped. Each new ID must prove zero pixel/cache/allocation/storage work in the ordinary effects-off JPEG path.
- Compare GR III single shooting, immediate playback, album and at least three consecutive photographs with stock positive/negative modes using the same camera/card/settings. Physical performance and color remain unverified until the user accepts the identified candidate.
- Deliver one traceable GR III test package and source/error report. Follow the established user-validation gate before any push, merge or production deployment.

## Remaining implementation decisions

Resolve exact Purple source and source-distribution policy; audit current production SHA through an available read-only entry (local administrator SSH currently rejects the available key). These do not permit weakening the ISP-only requirement. If a source or acceptable fit cannot be established, report that look as unresolved rather than enabling an invented replacement.
