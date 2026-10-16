# Morse code art

A Python command-line generator for pulsar-inspired stacked waveform artwork
made entirely from a repeating, configurable Morse message.

## Quick start

Requires Python 3.11 or newer. Run these commands from this folder:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python morse_art.py
```

This writes `output/morse-art.svg`, `output/morse-art.png`, and
`output/morse-art.json`. The default PNG is **2550 x 3300 pixels at 300 DPI**
(US Letter portrait). SVG is fully vector-based, with no embedded raster image
or font dependency. Both have an opaque background.

Rendering is offline: all three measured profiles are bundled in `data/`.
Only dependency installation needs internet access.

## Example

The finished default example will be saved in `examples/`.

## Design

- Default message: `I LOVE YOU`; configurable letters and digits.
- 80 rows, cream (`#F0EFEA`) on deep black (`#111111`).
- Dots, dashes and gaps use standard Morse ratios measured along the waveform.
- Words flow between rows without splitting; each row is justified by uniformly
  scaling its Morse unit.
- Foreground waveforms hide background lines, including behind Morse gaps.
  Visual depth takes priority over complete visibility of every symbol.
- Real pulse profiles can be blended, shifted and scaled for artistic effect.
  Synthetic variation is identified; the image is not a scientific pulse stack.
- Seeded reproducibility, vector SVG and US Letter portrait PNG at 300 DPI.
- Offline rendering from bundled, attributed profile data.

### Morse layout

A dot is a curved one-unit stroke; a dash is three units. Elements inside a
letter are separated by one unit, letters by three, and words by seven.
Butt caps avoid extending the visible symbol lengths into the gaps.

The repeated message is a continuous **word stream**, not restarted on every
row. The final word of a phrase is followed by the first word of the next
repetition. Within a row this boundary has the same seven-unit gap as any other
word boundary. A row break itself denotes a word boundary, without adding
leading or trailing gaps. Reading order is top to bottom, left to right.

Each row fits as many whole words as possible at the target `--unit`, then
uniformly scales *all* mark and gap lengths to exactly span its curve. A word
that is too long at the target size can shrink to `--min-unit`; if it still
cannot fit, rendering fails with an explicit error. Very short messages or long
words can therefore produce unusually large or small symbols.

Timing is exact along the sampled polyline before occlusion, rather than along
the horizontal axis. Foreground masks intentionally conceal some background
symbols, including through foreground Morse gaps; the visible image is not
guaranteed to be independently decodable. The last row ends on a complete word,
not necessarily a complete phrase.

### Signal composition

The default recipe blends two measured B1919+21 integrated profiles, at
142.9504 and 38.0737 MHz, with weights 0.65 and 0.35. A measured B0329+54 profile
is also available.

Profiles are baseline-subtracted, smoothed, centered, cropped, and normalized
before blending. Each contributes three shifted/stretched copies to a cluster
of central peaks. Seeded amplitude, width and position variations are correlated
between neighboring rows. Optional synthetic texture adds organic irregularity.
The outer edges remain quiet, and lower rows mask the rows behind them.

This is **art derived from observed average profiles**, not a plot of successive
measured pulses. Even with `--roughness 0`, the row variations are generated.
See [data/SOURCES.md](data/SOURCES.md) for original downloads, the exact
processing description, attribution, and CC BY 4.0 licensing.

## Customize

```sh
# A different message and random composition
python morse_art.py --message "ALWAYS WITH YOU" --seed 42 --output output/always

# Select a named pulsar profile; custom source selections default to equal weights
python morse_art.py --sources b0329-hba --output output/b0329

# Blend different pulsars with explicit relative weights
python morse_art.py --sources b1919-hba b0329-hba --weights 0.7 0.3 \
  --output output/blended

# Stronger peaks, more rows, and a slightly heavier stroke
python morse_art.py --lines 90 --peak-height 80 --stroke-width 0.6 \
  --roughness 0.18 --output output/taller

# Square canvas, vector only
python morse_art.py --width 8 --height 8 --formats svg --output output/square

# Replay saved settings, with an optional CLI override
python morse_art.py --config output/morse-art.json --output output/replayed
python morse_art.py --config output/morse-art.json --seed 42 --output output/variation
```

Use `--overwrite` to replace existing output files. Without it, existing files
are left untouched. Output names are **prefixes**: extensions are appended, not
replaced. Normal output goes in the Git-ignored `output/` folder.

`--config` accepts either a generated metadata file or a JSON object containing
configuration fields. Field names use underscores (e.g. `peak_height`), whereas
CLI flags use hyphens. CLI values override saved settings. Selecting sources on
the CLI resets their weights to equal values unless `--weights` is supplied.

Messages accept ASCII A-Z and 0-9, ignoring case and normalizing whitespace.
Punctuation, accents, emoji and empty messages produce explicit errors; they
are never silently removed.

### Main controls

| Flag | Default | Meaning |
|---|---|---|
| `--message` | `I LOVE YOU` | Repeated whole-word message |
| `--lines` | 80 | Stacked row count (1-500) |
| `--seed` | 1919 | Reproducible composition |
| `--sources` | `b1919-hba b1919-lba` | One or more bundled measured profiles |
| `--weights` | `0.65 0.35` | Non-negative relative source contributions |
| `--peak-height` | 64 | Maximum vertical rise, in points |
| `--signal-width` | 0.58 | Horizontal spread of the central signal |
| `--roughness` | 0.12 | Added synthetic texture strength (0-1) |
| `--drift` | 0.07 | Horizontal profile variation (0-0.5) |
| `--coherence` | 0.82 | Neighboring-row correlation (0 to less than 1) |
| `--stroke-width` | 0.5 | Stroke thickness, in points |
| `--unit` | 1.25 | Target dot/gap length, in points |
| `--min-unit` | 0.65 | Minimum permissible unit, in points |
| `--line-spacing` | automatic | Baseline separation, in points |
| `--width`, `--height` | 8.5, 11 | Canvas dimensions, in inches |
| `--margin` | 0.85 | Minimum outer margin, in inches |
| `--dpi` | 300 | PNG resolution (does not change SVG geometry) |
| `--foreground` | `#F0EFEA` | Opaque stroke color |
| `--background` | `#111111` | Opaque background color |
| `--samples` | 2048 | Polyline samples per row; more gives finer curves |

There are 72 points per inch. The default stack occupies a centered, roughly
square region within the Letter canvas. Explicit spacing overrides that
auto-fit; settings that exceed the available height are rejected. Stroke width
must not exceed the minimum Morse unit. Quote hex colors in shell commands.

Run `python morse_art.py --help` for all options, or `--list-sources` for pulsar
names and frequencies. The initial catalog contains three pinned observations,
not arbitrary online pulsar lookup.

## Reproducibility and sharing

The JSON sidecar contains effective settings, each row's words and unit size,
source URLs and SHA-256 hashes, attribution, processing notes, dependency
versions, and hashes of the finished SVG/PNG. Credits and settings are also
embedded in both image formats; there is no visible text on the artwork.

Identical settings, data, generator code and dependency versions produce
identical SVG/PNG bytes. Exact output across different library versions is not
guaranteed. For print, use actual size rather than a printer's "fit to page".

**Keep the data attribution and modification notice when sharing derived
artwork.** Retain the JSON sidecar or accompany the image with the credit in
`data/SOURCES.md`; image-processing tools may strip embedded metadata.

## Development and checkpoints

```sh
python -m pip install -r requirements-dev.txt
ruff check .
ruff format --check .
python -m unittest discover -s tests -v
```

Tests cover Morse timing, continuous word flow, arc-length geometry, deterministic
signals, real pixel-level depth occlusion, SVG/PNG exports, metadata replay,
input validation and overwrite protection. GitHub Actions runs these checks on
Python 3.11 and 3.14 for pushes and pull requests.

Project instructions in
[.github/copilot-instructions.md](.github/copilot-instructions.md) require
working checkpoint commits, pushes, and remote-commit verification. This is an
agent workflow policy, **not** a filesystem auto-sync service: uncommitted edits
are not automatically uploaded.

This repository is private. No software redistribution license has been selected;
the bundled scientific data retain their separate CC BY 4.0 terms.
