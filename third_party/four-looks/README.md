# Four ISP look reference inputs

These are traceable **approximations**, not measured film or GR III calibration.
Names identify the reference being approximated. No manufacturer endorses this
adaptation. Only offline tools evaluate the references; camera color uses ISP.

## Fujifilm Classic Negative / Classic Chrome

Original input: Fujifilm GFX ETERNA 55 archive v1.10, named 33-grid F-Log2 LUTs
version 1.00. Original LUTs are not redistributed: regeneration fetches and
SHA-256 checks the archive and member into an external cache. We found no explicit
redistribution grant in the archive; attribution is not a redistribution license.
Generated display adaptations and fitted coefficients are not original LUT files.

The model input is display sRGB, decoded using IEC sRGB, converted from D65
Rec.709 primaries to Rec.2020 (F-Gamut), with exposure scale exactly 1, then
encoded by the official F-Log2 equation. This treats decoded display values as
relative reflection; it does not recover radiance from JPEGs. Full-range code
values are used, with no legal-range scaling. Official LUT interpolation is
tetrahedral, red fastest on disk. Output is decoded with gamma 2.2 and re-encoded
as sRGB (white paper v1.01 page 13 recommends Rec.709, D65, gamma 2.2).

F-Log2: below 0.000889, `8.799461*x + 0.092864`; otherwise
`0.245281*log10(5.555556*x + 0.064829) + 0.384316`.
The official datasheet v1.1 gives 10-bit values 95/400/570 at 0/18/90% reflection.

## Kodak 2383

MIT Spectral Film LUT source by Jan Lohse is already vendored in
`third_party/spectral-film-lut`, with its license retained. Its KODAK_2383 model
digitizes the Kodak print-stock characteristic, sensitivity and dye-density
curves. Kodak's H-1-2383 data sheet is the descriptive source, not redistributed.

2383 is a **print stock**, placed in ECN2 solely as requested by the user. This
display adaptation avoids silently selecting a camera-negative stock: decode
sRGB, form an ideal neutral negative `APD = LAD + 0.6*log10(max(linear,1e-6)/0.18)`
with upstream LAD `[0.78,0.84,0.79]`, then use the original `print_from_apd`,
non-idealized characteristic curves, 6500 K projection, no white compensation,
no white balancing, and Rec.709/sRGB output. The ideal negative slope and exposure
mapping are explicit modeling assumptions. They are not Kodak measured values.

## LomoChrome Purple

The official Film Guide's physical page 2 compares ISO100 Purple against Color
Negative100 using photographed 24-patch charts. `purple-chart.json` preserves
the original PDF hash, embedded JPEG hashes/dimensions, exact 20x20 rectangles,
median RGB, standard deviation and 10th/90th percentiles for every paired patch.
The photographs are linked and fetched for regeneration, not redistributed.

We interpret the numeric JPEG samples as sRGB, although the guide does not give
scanner, illumination, white balance, exposure equality, ICC or spectral data.
The guide itself calls its chart an estimated indication. Thus within-patch
spread understates total uncertainty. Color Negative100 is the comparison
baseline, not an identity camera or known reflectance measurement.

Indices 2,8,14,20 (zero-based row-major) are held out of source construction.
The remaining 20 pairs define a SciPy thin-plate-spline RBF with affine tail and
smoothing 0.02, clipped to display RGB. This interpolation and extrapolation is
authored. Source holdout patch error is reported independently from ISP fit
error; neither certifies physical accuracy or other ISO ratings. No invented
channel swap replaces the observations. The saltyKaane LUT-Generator candidate
was rejected: its cube exporter ignores all hue-adjustment settings, so its
Purple preset does not implement the advertised green-to-purple change.

## Reproduce

Run `.venv/bin/python scripts/build_gr3_four_looks_reference.py` and then
`.venv/bin/python scripts/fit_gr3_four_looks_native.py`. Set
`M10V_FOUR_LOOKS_CACHE` to an external cache if desired. Original inputs are
hash-pinned. Normal firmware builds run the standard-library-only verifier and
need neither network nor original manufacturer files. Fitting uses floating
references directly before any 15-cube preview downsampling; all metrics are
after quantizing native coefficients, with independent random seed.
