# Original JPEG pointer alignment

Offline original ARM evidence for hash-pinned GR III 2.10 and GR IIIx 1.60.
No firmware activation, image DMA, silicon response or performance is tested.

Original JPEG driver `0x53791044` calls Y setter `0x5379228c`, chroma setter
`0x537922e4` and encoded-output setter `0x5379233c`. Each starts with
`TST r1,#7` and asserts for a pointer that is not 8-byte aligned. The setters
write the complete pointer to RAM-backed register addresses `0x298c0430`,
`0x298c0434` and `0x298c0440`; they do not clear low address bits.

The probe executes the complete original driver with Y/C offsets 0, 2, 4, 6,
8, and executes each of the three original setters independently with those
offsets. Both ROMs give no alignment assertion for 0/8; 2/4/6 trigger two
assertions in the driver and one per individual setter. The assertion service
is explicitly substituted with a returning recorder. Consequently an invalid
pointer appearing in fixture RAM after an assertion is **not acceptance**.

Require 8-byte alignment for all JPEG pointer admission. Geometry and plane
placement must satisfy this together without changing the complete inner image.
An aligned canvas does not establish alignment support for a differently offset
inner source; R2Y, copy, resize and other consumers need separate contracts.
The two originals have the same setter span `0x5379228c..0x53792394` SHA256:
`c26321cb8eb388a62cd9160782de60064db6beaa1fa064c06059bf41a2d28887`.

Restore the official fixtures using the recipe in
`gr3-gr3x-border-iip-20261027.md`, then run from the repository root:

```sh
/Users/zhaoo/Desktop/code/zhaoo/m10v/.venv/bin/python -m unittest tests.test_gr3_border_jpeg_alignment -v
/Users/zhaoo/Desktop/code/zhaoo/m10v/.venv/bin/python scripts/probe_gr3_border_jpeg_alignment.py --model gr3 --rtos builds/gr3-border-iip-20261027/gr3-official-rtos.bin --out builds/gr3-border-iip-20261027/gr3-jpeg-alignment.json
/Users/zhaoo/Desktop/code/zhaoo/m10v/.venv/bin/python scripts/probe_gr3_border_jpeg_alignment.py --model gr3x --rtos builds/gr3-border-iip-20261027/gr3x-official-rtos.bin --out builds/gr3-border-iip-20261027/gr3x-jpeg-alignment.json
```
