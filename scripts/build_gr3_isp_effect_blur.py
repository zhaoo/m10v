"""BUILD-HOST optical softening fit; no camera pixel processing.

Positive sharp-core + broad-scatter PSF, fitted to assumed native octave bands.
An artistic old-lens/film imaging-chain approximation, not measured film MTF.
"""
import math

from scripts.build_gr3_digital_hdf import ROWS

MODEL = 'Positive core + scatter PSF mixture, 11 octave bands Q10; artistic old optical chain fit'
CORE_SIGMAS = (.18, .30, .46)
SCATTER_WEIGHTS = (.18, .32, .48)
SCATTER_SIGMAS = (1.5, 3., 6.)
REFERENCES = (
 'https://tiffen.com/pages/diffusion-guide',
 'https://www.edmundoptics.com/knowledge-center/application-notes/optics/introduction-to-modulation-transfer-function/',
 'https://www.kodak.com/content/products-brochures/Film/kodak-essential-reference-guide-for-filmmakers.pdf')
FREQUENCIES = tuple(.5 / (2**i) for i in range(11))


def native_value(hdf, gain, radius):
    """HDF 0..3 × blur strength 1..3 × range 0..2 -> native value 8..43."""
    if (any(type(v) is not int for v in (hdf, gain, radius)) or
            hdf not in range(4) or gain not in range(1, 4) or radius not in range(3)):
        raise ValueError('expected HDF 0..3, blur strength 1..3, range 0..2')
    return 8 + hdf * 9 + (gain - 1) * 3 + radius


def _rows():
    rows, identities = [], []
    for hdf in range(4):
        hdf_row = ROWS[hdf - 1] if hdf else (1024,) * 11
        for gain in range(1, 4):
            for radius in range(3):
                core,scatter,weight = CORE_SIGMAS[gain-1],SCATTER_SIGMAS[radius],SCATTER_WEIGHTS[gain-1]
                attenuation = tuple(1024 if i >= 9 else max(0, min(1024,
                    round(1024 * ((1-weight)*math.exp(-2*math.pi**2*core**2*frequency**2)+
                                  weight*math.exp(-2*math.pi**2*scatter**2*frequency**2)))))
                    for i, frequency in enumerate(FREQUENCIES))
                row = tuple((a * b + 512) // 1024 for a, b in zip(hdf_row, attenuation))
                value = native_value(hdf, gain, radius)
                rows.append(row)
                identities.append(dict(hdf_grade=hdf, blur_strength=gain, blur_range=radius,
                    native_value=value, native_r8=value + 4, table_index=value - 5,
                    core_sigma=core,scatter_sigma=scatter,scatter_weight=weight,
                    attenuation_q10=attenuation,gains_q10=row))
    return tuple(rows), tuple(identities)


BLUR_ROWS, BLUR_ROW_IDENTITIES = _rows()


def manifest():
    return dict(model=MODEL, native_parameter_range=[8, 43], native_r8_range=[12, 47],
                table_index_range=[3, 38], rows=BLUR_ROW_IDENTITIES,
                frequencies=FREQUENCIES,references=REFERENCES,preserved_unity_attenuation_bands=[9, 10],
                camera_pixel_generation=False, hardware_appearance_pending=True,
                disclaimer='Offline coefficient study only; native low-pass response and hardware appearance pending validation.')
