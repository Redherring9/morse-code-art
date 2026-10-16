# Bundled observed pulsar profiles

These three JSON files are unmodified downloads from the University of
Manchester's [EPN Database of Pulsar Profiles](https://psrweb.jb.man.ac.uk/epndb/).
Retrieved 2026-10-16. Each file's `hdr.license` is `c_l_ccby`, which the
[archive license documentation](https://psrweb.jb.man.ac.uk/epndb/about.html)
identifies as **Creative Commons Attribution 4.0 International**.

Copyright remains with the original data authors. These files are **not**
public domain and are not covered by a software license.

| Local source key | Pulsar | Frequency | Archive observation |
|---|---|---|---|
| `b1919-hba` | B1919+21 / J1921+2153 | 142.9504 MHz | `B1919+21_L32630_HBA.prof.epn` |
| `b1919-lba` | B1919+21 / J1921+2153 | 38.0737 MHz | `B1919+21_L32726_LBA.prof.epn` |
| `b0329-hba` | B0329+54 / J0332+5434 | 142.9504 MHz | `B0329+54_L32575_HBA.prof.epn` |

## Attribution

Pilia, M. et al. (2016), *Wide-band, low-frequency pulse profiles of 100 radio
pulsars with LOFAR*, Astronomy & Astrophysics, 586, A92.
<https://doi.org/10.1051/0004-6361/201425196>

The archive identifies this contribution as `phs+15` and lists the reference
year as 2015; the journal publication is 2016.

Part of this project has made use of the EPN Database of Pulsar Profiles
maintained by the University of Manchester. Profiles were obtained under the
[Creative Commons Attribution 4.0 International license](https://creativecommons.org/licenses/by/4.0/).

## Original downloads

- <https://psrweb.jb.man.ac.uk/epndb/json/phs+15/J1921+2153/B1919+21_L32630_HBA.prof.epn.json>
- <https://psrweb.jb.man.ac.uk/epndb/json/phs+15/J1921+2153/B1919+21_L32726_LBA.prof.epn.json>
- <https://psrweb.jb.man.ac.uk/epndb/json/phs+15/J0332+5434/B0329+54_L32575_HBA.prof.epn.json>

## Changes in generated artwork

The source files remain unchanged. Rendering subtracts the median baseline,
smooths with a nine-bin Gaussian kernel (sigma one bin), clips negative values,
normalizes, centers and crops at a 4% peak threshold with 20% padding, and
tapers the crop edges. Blending, stretching, shifting, amplitude modulation,
and optional synthetic texture then create an **artistic composition**.
Rows are not individual observed pulses. Metadata records source hashes,
credits and the applied settings.

Keep attribution and a notice of modifications when sharing derived artwork.
