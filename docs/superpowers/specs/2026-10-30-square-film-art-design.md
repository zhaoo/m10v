# Square film artwork and identity

User approved the A classic packaging square concept and requested implementation across the workbench, camera library, shooting filter/ADJ display and playback, plus custom LUT identity fixes.

## Design

- Square packaging art with dominant film name, legible speed, characteristic colors and distinct motifs. Reference: `/Users/zhaoo/.codex/generated_images/01a18ab8-e1bc-7a21-8400-c6e81eed7d60/exec-f7d8cac8-3b93-4ac3-96c9-3b84959e8bd7.png`.
- Use the existing editable artwork generation system, sharing identity/palette between large square cards and dedicated compact icons. Small icons omit decorative detail and prioritize distinctive model text; adjacent names remain full names.
- Large camera cards become square, fitted to the existing 720x480 screen with no overlap. Web icons use the same artwork language throughout selectors, catalog and slots.
- Resolve imported names for every supported slot, including appended slots, without reading SD on the capture path.
- Playback must show the identity recorded by the photograph, never borrow the currently selected film. Investigate the metadata format; preserve old-photo compatibility and expose unknown historic identity honestly.

## Protected behavior

Preserve film IDs, catalog order, custom banks, journals, source LUT data, ISP and capture performance, image parameters, and other camera functions. No production publication before identifiable camera test candidate validation. Offline tests are not physical camera acceptance.

## Verification

Exercise actual ARM resource/menu adapters, custom names in all slots, recorded playback after selection changes, square dimensions, sprite/catalog coverage, web selectors and production native export. Deliver screenshots plus candidate manifest and hashes where build inputs are available.
