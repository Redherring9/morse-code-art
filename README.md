# Morse code art

A Python command-line generator for pulsar-inspired stacked waveform artwork
made entirely from a repeating, configurable Morse message.

## Agreed design

- Default message: `I LOVE YOU`; configurable letters and digits.
- About 80 rows, cream (`#F0EFEA`) on deep black (`#111111`).
- Dots, dashes and gaps use standard Morse ratios measured along the waveform.
- Words flow between rows without splitting; each row is justified by uniformly
  scaling its Morse unit.
- Foreground waveforms hide background lines, including behind Morse gaps.
  Visual depth takes priority over complete visibility of every symbol.
- Real pulse profiles can be blended, shifted and scaled for artistic effect.
  Synthetic variation is identified; the image is not a scientific pulse stack.
- Seeded reproducibility, vector SVG and US Letter portrait PNG at 300 DPI.
- Offline rendering from bundled, attributed profile data.

Implementation and usage instructions will accompany the working generator.
