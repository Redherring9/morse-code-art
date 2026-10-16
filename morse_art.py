#!/usr/bin/env python3
"""Render depth-stacked, justified Morse waveforms from real pulsar profiles."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import platform
import tempfile
from dataclasses import asdict, dataclass, fields
from pathlib import Path

import matplotlib
import numpy as np
from matplotlib import colors
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.collections import LineCollection
from matplotlib.figure import Figure
from matplotlib.patches import Polygon
from numpy.typing import NDArray

DATA_DIR = Path(__file__).resolve().parent / "data"
SOURCE_PATHS = {
    "b1919-hba": "phs+15/J1921+2153/B1919+21_L32630_HBA.prof.epn",
    "b1919-lba": "phs+15/J1921+2153/B1919+21_L32726_LBA.prof.epn",
    "b0329-hba": "phs+15/J0332+5434/B0329+54_L32575_HBA.prof.epn",
}
EPN_URL = "https://psrweb.jb.man.ac.uk/epndb/"
DATA_CITATION = (
    "Pilia, M. et al. (2016), Wide-band, low-frequency pulse profiles of "
    "100 radio pulsars with LOFAR, A&A 586, A92. "
    "https://doi.org/10.1051/0004-6361/201425196"
)
Array = NDArray[np.float64]

MORSE = dict(
    zip(
        "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789",
        (
            ".- -... -.-. -.. . ..-. --. .... .. .--- -.- .-.. -- -. "
            "--- .--. --.- .-. ... - ..- ...- .-- -..- -.-- --.. "
            "----- .---- ..--- ...-- ....- ..... -.... --... ---.. ----."
        ).split(),
        strict=True,
    )
)


@dataclass(frozen=True)
class Element:
    """One uninterrupted mark or gap, in standard Morse units."""

    mark: bool
    units: int


@dataclass(frozen=True)
class Row:
    words: tuple[str, ...]
    elements: tuple[Element, ...]
    unit_length: float
    next_word: int

    @property
    def units(self) -> int:
        return sum(element.units for element in self.elements)


@dataclass(frozen=True)
class Profile:
    key: str
    phase: Array
    intensity: Array
    provenance: dict


@dataclass(frozen=True)
class Config:
    message: str = "I LOVE YOU"
    lines: int = 80
    seed: int = 1919
    sources: tuple[str, ...] = ("b1919-hba", "b1919-lba")
    weights: tuple[float, ...] = (0.65, 0.35)
    width: float = 8.5
    height: float = 11.0
    dpi: int = 300
    margin: float = 0.85
    peak_height: float = 64.0
    line_spacing: float | None = None
    stroke_width: float = 0.5
    unit: float = 1.25
    min_unit: float = 0.65
    signal_width: float = 0.58
    roughness: float = 0.12
    drift: float = 0.07
    coherence: float = 0.82
    samples: int = 2048
    foreground: str = "#F0EFEA"
    background: str = "#111111"

    def validate(self) -> None:
        if not isinstance(self.message, str):
            raise ValueError("Message must be a string.")
        normalize_message(self.message)
        for name, low, high in (
            ("lines", 1, 500),
            ("seed", 0, 2**63 - 1),
            ("dpi", 72, 1200),
            ("samples", 256, 8192),
        ):
            value = getattr(self, name)
            if type(value) is not int or not low <= value <= high:
                raise ValueError(f"{name} must be an integer between {low} and {high}.")
        for name in (
            "width",
            "height",
            "margin",
            "peak_height",
            "stroke_width",
            "unit",
            "min_unit",
            "signal_width",
            "roughness",
            "drift",
            "coherence",
        ):
            value = getattr(self, name)
            if type(value) not in (int, float) or not math.isfinite(value):
                raise ValueError(f"{name} must be a finite number.")
        if not 1 <= self.width <= 40 or not 1 <= self.height <= 40:
            raise ValueError("Canvas width and height must be between 1 and 40 inches.")
        if self.width * self.height * self.dpi**2 > 100_000_000:
            raise ValueError("Canvas exceeds the 100 megapixel rendering limit.")
        if self.margin <= 0 or self.margin * 2 >= min(self.width, self.height):
            raise ValueError("Margin must be positive and leave usable space on the canvas.")
        if not 0.1 <= self.min_unit <= self.unit:
            raise ValueError("Morse units must satisfy 0.1 <= min_unit <= unit (points).")
        if not 0 < self.stroke_width <= self.min_unit:
            raise ValueError("Stroke width must be positive and no larger than min_unit (points).")
        if not 0.1 <= self.signal_width <= 1:
            raise ValueError("signal_width must be between 0.1 and 1.")
        if not 0 <= self.roughness <= 1 or not 0 <= self.drift <= 0.5:
            raise ValueError("roughness must be between 0 and 1; drift between 0 and 0.5.")
        if not 0 <= self.coherence < 1:
            raise ValueError("coherence must be at least zero and less than one.")
        if self.peak_height < 0:
            raise ValueError("peak_height must be non-negative (points).")
        if self.line_spacing is not None and (
            type(self.line_spacing) not in (int, float)
            or not math.isfinite(self.line_spacing)
            or self.line_spacing <= 0
        ):
            raise ValueError("line_spacing must be finite and positive (points).")
        for name in ("foreground", "background"):
            color = getattr(self, name)
            if not isinstance(color, str) or not colors.is_color_like(color):
                raise ValueError(f"{name} must be a valid Matplotlib color.")
            if colors.to_rgba(color)[3] != 1:
                raise ValueError(f"{name} must be opaque.")
        if colors.to_rgba(self.foreground) == colors.to_rgba(self.background):
            raise ValueError("Foreground and background colors must differ.")
        if (
            not isinstance(self.sources, (list, tuple))
            or not self.sources
            or any(not isinstance(key, str) or key not in SOURCE_PATHS for key in self.sources)
        ):
            raise ValueError(f"Choose one or more source keys from {', '.join(SOURCE_PATHS)}.")
        if (
            not isinstance(self.weights, (list, tuple))
            or len(self.weights) != len(self.sources)
            or any(
                type(w) not in (int, float) or not math.isfinite(w) or w < 0 for w in self.weights
            )
            or not math.isfinite(sum(self.weights))
            or sum(self.weights) <= 0
        ):
            raise ValueError("Supply one non-negative weight per source, with a positive total.")
        canvas_geometry(self)


@dataclass(frozen=True)
class Waveform:
    x: Array
    y: Array

    @property
    def arc(self) -> Array:
        return np.concatenate(([0.0], np.cumsum(np.hypot(np.diff(self.x), np.diff(self.y)))))


def load_profile(key: str, data_dir: Path = DATA_DIR) -> Profile:
    """Read an unchanged EPN archive JSON file and retain its provenance."""
    if key not in SOURCE_PATHS:
        raise ValueError(f"Unknown source {key!r}; choose from {', '.join(SOURCE_PATHS)}.")
    path = data_dir / f"{key}.json"
    raw = path.read_bytes()
    try:
        data = json.loads(raw)
        header = data["hdr"]
        samples = np.asarray(data["series"]["I"], dtype=float)
        if header["license"] != "c_l_ccby":
            raise ValueError(f"Source {key!r} does not declare the expected CC BY 4.0 license.")
        name = header["name"]
        frequency = float(header["freq"])
        reference = header["ref"]
    except (KeyError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Malformed EPN profile {path}: {exc}") from exc
    if (
        samples.ndim != 2
        or samples.shape[1] != 2
        or samples.shape[0] < 16
        or not np.isfinite(samples).all()
        or not np.all(np.diff(samples[:, 0]) > 0)
        or np.ptp(samples[:, 1]) <= 0
        or not math.isfinite(frequency)
        or frequency <= 0
    ):
        raise ValueError(f"Source {key!r} needs finite, ordered phase/intensity samples.")
    return Profile(
        key,
        samples[:, 0],
        samples[:, 1],
        {
            "key": key,
            "pulsar": name,
            "frequency_mhz": frequency,
            "data_product": "observed integrated total-intensity profile",
            "url": f"{EPN_URL}json/{SOURCE_PATHS[key]}.json",
            "sha256": hashlib.sha256(raw).hexdigest(),
            "archive_reference": reference,
            "citation": DATA_CITATION,
            "license": "CC BY 4.0",
            "license_url": "https://creativecommons.org/licenses/by/4.0/",
            "archive_acknowledgement": (
                "Profiles obtained from the EPN Database of Pulsar Profiles, "
                "maintained by the University of Manchester, under CC BY 4.0."
            ),
        },
    )


def prepare_profile(profile: Profile) -> tuple[Array, Array]:
    """Baseline-subtract, smooth, center and crop a profile for artistic blending."""
    signal = profile.intensity - np.median(profile.intensity)
    signal = np.roll(signal, len(signal) // 2 - int(np.argmax(signal)))
    kernel_x = np.arange(-4, 5, dtype=float)
    kernel = np.exp(-0.5 * kernel_x**2)
    signal = np.convolve(signal, kernel / kernel.sum(), mode="same")
    signal = np.maximum(signal, 0)
    if signal.max() <= 0:
        raise ValueError(
            f"Source {profile.key!r} has no positive pulse after baseline subtraction."
        )
    signal /= signal.max()
    significant = np.flatnonzero(signal >= 0.04)
    padding = max(4, int((significant[-1] - significant[0]) * 0.2))
    start = max(0, int(significant[0]) - padding)
    stop = min(len(signal), int(significant[-1]) + padding + 1)
    cropped = signal[start:stop].copy()
    # Taper cropped edges to zero so profile copies meet their quiet surroundings.
    taper = min(padding, len(cropped) // 2)
    cropped[:taper] *= np.linspace(0, 1, taper)
    cropped[-taper:] *= np.linspace(1, 0, taper)
    return np.linspace(-1, 1, len(cropped)), cropped


def normalize_message(message: str) -> str:
    # Validate before uppercasing so Unicode expansions cannot change the message.
    invalid = sorted(
        {
            char
            for char in message
            if not char.isspace() and char not in MORSE and char not in "abcdefghijklmnopqrstuvwxyz"
        }
    )
    if invalid:
        raise ValueError(f"Unsupported message characters: {', '.join(repr(c) for c in invalid)}")
    normalized = " ".join(message.upper().split())
    if not normalized:
        raise ValueError("Message must contain at least one letter or digit.")
    return normalized


def encode_word(word: str) -> tuple[Element, ...]:
    if not word or any(char not in MORSE for char in word):
        raise ValueError("Words must contain uppercase ASCII letters or digits.")
    elements = []
    for letter_index, letter in enumerate(word):
        if letter_index:
            elements.append(Element(False, 3))
        for symbol_index, symbol in enumerate(MORSE[letter]):
            if symbol_index:
                elements.append(Element(False, 1))
            elements.append(Element(True, 1 if symbol == "." else 3))
    return tuple(elements)


def layout_row(
    message: str,
    start_word: int,
    arc_length: float,
    target_unit: float,
    min_unit: float,
) -> Row:
    """Fill one row with whole words from a cyclic message, then justify it."""
    if not all(math.isfinite(v) and v > 0 for v in (arc_length, target_unit, min_unit)):
        raise ValueError("Arc length and Morse unit sizes must be finite and positive.")
    if min_unit > target_unit:
        raise ValueError("Minimum Morse unit cannot exceed the target unit.")
    if start_word < 0:
        raise ValueError("Starting word index must be non-negative.")
    words = normalize_message(message).split()
    encoded = [encode_word(word) for word in words]
    lengths = [sum(element.units for element in word) for word in encoded]
    capacity = arc_length / target_unit
    selected: list[str] = []
    elements: list[Element] = []
    used = 0
    index = start_word % len(words)
    while True:
        extra = lengths[index] + (7 if selected else 0)
        if selected and used + extra > capacity:
            break
        if not selected and lengths[index] * min_unit > arc_length:
            raise ValueError(
                f"Word {words[index]!r} cannot fit at the minimum Morse unit; "
                "reduce --min-unit, widen the artwork, or shorten the word."
            )
        if selected:
            elements.append(Element(False, 7))
        selected.append(words[index])
        elements.extend(encoded[index])
        used += extra
        index = (index + 1) % len(words)
        if used >= capacity:
            break
    return Row(tuple(selected), tuple(elements), arc_length / used, index)


def canvas_geometry(config: Config) -> tuple[float, float, float]:
    """Return width, bottom baseline and row spacing, all in physical points."""
    usable_width = (config.width - 2 * config.margin) * 72 - config.stroke_width
    available = (config.height - 2 * config.margin) * 72 - config.stroke_width
    if usable_width <= 0 or available <= 0 or config.peak_height > available:
        raise ValueError("Margins, stroke width and peak height leave no usable artwork area.")
    if config.line_spacing is None:
        block_height = min(usable_width, available)
        if config.lines > 1 and block_height <= config.peak_height:
            raise ValueError("Peak height leaves no room for stacked rows.")
        spacing = (
            (block_height - config.peak_height) / (config.lines - 1) if config.lines > 1 else 0
        )
    else:
        spacing = config.line_spacing
    occupied = config.peak_height + spacing * (config.lines - 1)
    if occupied > available + 1e-9:
        raise ValueError("Line spacing, count and peak height do not fit inside the margins.")
    bottom = config.margin * 72 + config.stroke_width / 2 + (available - occupied) / 2
    return usable_width, bottom, spacing


def generate_waveforms(config: Config, profiles: list[Profile]) -> list[Waveform]:
    """Blend observed shapes with seeded, correlated artistic row variation."""
    config.validate()
    if [profile.key for profile in profiles] != list(config.sources):
        raise ValueError("Loaded profiles must match the configured source order.")
    prepared = [prepare_profile(profile) for profile in profiles]
    weights = np.asarray(config.weights, dtype=float)
    weights /= weights.sum()
    rng = np.random.default_rng(config.seed)
    width, bottom, spacing = canvas_geometry(config)
    x = np.linspace(
        config.margin * 72 + config.stroke_width / 2,
        config.margin * 72 + config.stroke_width / 2 + width,
        config.samples,
    )
    t = np.linspace(-1, 1, config.samples)
    z = t / config.signal_width
    envelope = np.exp(-((z / 0.78) ** 6))
    edge_taper = np.maximum(0, 1 - t**2) ** 2
    state = rng.normal(size=(len(profiles), 3, 3))
    texture = rng.normal(size=161)
    texture_x = np.linspace(-1, 1, len(texture))
    kernel_x = np.arange(-8, 9, dtype=float)
    kernel = np.exp(-0.5 * (kernel_x / 2.5) ** 2)
    kernel /= kernel.sum()
    waveforms = []
    for row_index in range(config.lines):
        innovation = math.sqrt(1 - config.coherence**2)
        state = config.coherence * state + innovation * rng.normal(size=state.shape)
        texture = config.coherence * texture + innovation * rng.normal(size=texture.shape)
        pulse = np.zeros(config.samples)
        for source_index, (phase, intensity) in enumerate(prepared):
            source_signal = np.zeros(config.samples)
            for component, (center, scale, amplitude) in enumerate(
                ((-0.34, 0.34, 0.7), (0.02, 0.43, 1.0), (0.36, 0.3, 0.65))
            ):
                variation = np.tanh(state[source_index, component])
                center += config.drift * variation[0]
                scale *= 1 + 0.22 * variation[1]
                amplitude *= 1 + 0.35 * variation[2]
                source_signal += amplitude * np.interp(
                    (z - center) / scale, phase, intensity, left=0, right=0
                )
            pulse += weights[source_index] * source_signal
        jitter = np.convolve(np.interp(t, texture_x, texture), kernel, mode="same")
        pulse = np.maximum(0, pulse + config.roughness * jitter * envelope) * edge_taper
        # Keep the height bounded without normalizing away all row-to-row variation.
        pulse /= max(1.5, float(pulse.max()))
        baseline = bottom + (config.lines - row_index - 1) * spacing
        waveforms.append(Waveform(x.copy(), baseline + config.peak_height * pulse))
    return waveforms


def morse_segments(waveform: Waveform, row: Row) -> list[Array]:
    """Cut marks at exact polyline arc distances, preserving internal vertices."""
    arc = waveform.arc
    if not math.isclose(row.units * row.unit_length, float(arc[-1]), rel_tol=1e-10):
        raise ValueError("Morse layout must be justified to this waveform's arc length.")
    position = 0.0
    segments = []
    for element in row.elements:
        end = min(float(arc[-1]), position + element.units * row.unit_length)
        if element.mark:
            first = np.searchsorted(arc, position, side="right")
            last = np.searchsorted(arc, end, side="left")
            start_point = [
                np.interp(position, arc, waveform.x),
                np.interp(position, arc, waveform.y),
            ]
            end_point = [np.interp(end, arc, waveform.x), np.interp(end, arc, waveform.y)]
            interior = np.column_stack((waveform.x[first:last], waveform.y[first:last]))
            segments.append(np.vstack((start_point, interior, end_point)))
        position = end
    return segments


def build_figure(config: Config, waveforms: list[Waveform], rows: list[Row]) -> Figure:
    figure = Figure(
        figsize=(config.width, config.height), dpi=config.dpi, facecolor=config.background
    )
    FigureCanvasAgg(figure)
    axes = figure.add_axes((0, 0, 1, 1))
    axes.set_xlim(0, config.width * 72)
    axes.set_ylim(0, config.height * 72)
    axes.set_axis_off()
    for index, (waveform, row) in enumerate(zip(waveforms, rows, strict=True)):
        boundary = np.column_stack((waveform.x, waveform.y))
        vertices = np.vstack(([waveform.x[0], 0], boundary, [waveform.x[-1], 0]))
        mask = Polygon(
            vertices,
            closed=True,
            facecolor=config.background,
            edgecolor="none",
            antialiased=False,
            zorder=index * 2 + 1,
        )
        mask.set_gid(f"occlusion-row-{index:03d}")
        axes.add_patch(mask)
        strokes = LineCollection(
            morse_segments(waveform, row),
            colors=config.foreground,
            linewidths=config.stroke_width,
            capstyle="butt",
            joinstyle="round",
            zorder=index * 2 + 2,
        )
        strokes.set_gid(f"morse-row-{index:03d}")
        axes.add_collection(strokes)
    return figure


def render(
    config: Config,
    output: Path,
    formats: tuple[str, ...] = ("svg", "png"),
    overwrite: bool = False,
) -> list[Path]:
    """Write artwork and replayable provenance, staging files before replacement."""
    config.validate()
    if (
        not formats
        or len(set(formats)) != len(formats)
        or any(fmt not in ("svg", "png") for fmt in formats)
    ):
        raise ValueError("Formats must be a unique selection of svg and png.")
    destinations = [Path(f"{output}.{suffix}") for suffix in (*formats, "json")]
    for path in destinations:
        if path.exists() and not path.is_file():
            raise ValueError(f"Output path is not a regular file: {path}")
        if path.exists() and not overwrite:
            raise FileExistsError(f"Output already exists: {path}. Use --overwrite to replace it.")
    profiles = [load_profile(key) for key in config.sources]
    waveforms = generate_waveforms(config, profiles)
    rows = []
    cursor = 0
    for waveform in waveforms:
        row = layout_row(
            config.message, cursor, float(waveform.arc[-1]), config.unit, config.min_unit
        )
        rows.append(row)
        cursor = row.next_word
    effective = asdict(config)
    effective["message"] = normalize_message(config.message)
    metadata = {
        "schema_version": 1,
        "config": effective,
        "description": (
            "Artistic blend of observed integrated pulsar profiles with synthetic "
            "row variation; not a measured sequence of individual pulses. "
            "Morse is justified along arc length, wraps at word boundaries, and "
            "is intentionally occluded by foreground waveforms."
        ),
        "processing": (
            "Median baseline subtraction, Gaussian smoothing (sigma=1 bin, 9 bins), "
            "negative clipping, peak normalization and centering, crop at 4% peak "
            "with 20% padding, tapered crop edges; three shifted/stretched copies "
            "per source, weighted blending, correlated amplitude/width/drift "
            "variation, optional synthetic texture, central/edge masking."
        ),
        "sources": [profile.provenance for profile in profiles],
        "versions": {
            "python": platform.python_version(),
            "numpy": np.__version__,
            "matplotlib": matplotlib.__version__,
        },
        "rows": [
            {
                "index": index,
                "words": list(row.words),
                "units": row.units,
                "unit_points": row.unit_length,
                "arc_points": float(waveform.arc[-1]),
                "next_word": row.next_word,
            }
            for index, (waveform, row) in enumerate(zip(waveforms, rows, strict=True))
        ],
    }
    embedded = json.dumps(metadata, sort_keys=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".morse-art-", dir=output.parent) as directory:
        staged = []
        with matplotlib.rc_context({"svg.hashsalt": "morse-art-v1", "path.simplify": False}):
            figure = build_figure(config, waveforms, rows)
            for fmt, destination in zip(formats, destinations[:-1], strict=True):
                path = Path(directory) / destination.name
                file_metadata = {"Title": "Morse pulsar artwork", "Description": embedded}
                if fmt == "svg":
                    file_metadata["Date"] = None
                    file_metadata["Creator"] = "morse-code-art"
                figure.savefig(
                    path,
                    format=fmt,
                    dpi=config.dpi,
                    metadata=file_metadata,
                    facecolor=config.background,
                    transparent=False,
                )
                staged.append(path)
            figure.clear()
        metadata["outputs"] = {
            path.suffix[1:]: {
                "file": path.name,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
            for path in staged
        }
        manifest = Path(directory) / destinations[-1].name
        manifest.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        staged.append(manifest)
        for source, destination in zip(staged, destinations, strict=True):
            source.replace(destination)
    return destinations


def argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        argument_default=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--config", type=Path, help="Replay a saved output JSON, or a config object"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("output/morse-art"),
        help="Output prefix (extensions are appended)",
    )
    parser.add_argument("--formats", nargs="+", choices=("svg", "png"), default=["svg", "png"])
    parser.add_argument("--overwrite", action="store_true", default=False)
    parser.add_argument("--list-sources", action="store_true", default=False)
    parser.add_argument(
        "--message", help="ASCII letters/digits and whitespace; default: I LOVE YOU"
    )
    parser.add_argument(
        "--sources",
        nargs="+",
        choices=tuple(SOURCE_PATHS),
        help="Observed profiles to blend; default: b1919-hba b1919-lba",
    )
    parser.add_argument(
        "--weights",
        nargs="+",
        type=float,
        help="One weight per source; default: 0.65 0.35 (equal for custom sources)",
    )
    for name, help_text in (
        ("lines", "Stacked row count"),
        ("seed", "Reproducible random seed"),
        ("dpi", "PNG dots per inch"),
        ("samples", "Waveform samples per row"),
    ):
        parser.add_argument(
            f"--{name}", type=int, help=f"{help_text}; default: {getattr(Config(), name)}"
        )
    for name, help_text in (
        ("width", "Canvas width in inches"),
        ("height", "Canvas height in inches"),
        ("margin", "Minimum canvas margin in inches"),
        ("peak_height", "Maximum rise in points"),
        ("line_spacing", "Baseline separation in points (otherwise auto-fit a square artwork)"),
        ("stroke_width", "Morse stroke width in points"),
        ("unit", "Target Morse unit in points"),
        ("min_unit", "Minimum Morse unit in points"),
        ("signal_width", "Central signal width fraction"),
        ("roughness", "Synthetic texture strength [0, 1]"),
        ("drift", "Profile drift [0, 0.5]"),
        ("coherence", "Neighboring-row correlation [0, 1)"),
    ):
        parser.add_argument(
            f"--{name.replace('_', '-')}",
            type=float,
            help=f"{help_text}; default: {getattr(Config(), name)}",
        )
    parser.add_argument("--foreground", help="Opaque stroke color; default: #F0EFEA")
    parser.add_argument("--background", help="Opaque canvas color; default: #111111")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = argument_parser()
    args = vars(parser.parse_args(argv))
    try:
        if args.pop("list_sources"):
            for key in SOURCE_PATHS:
                info = load_profile(key).provenance
                print(f"{key:12} {info['pulsar']}  {info['frequency_mhz']:g} MHz  CC BY 4.0")
            return 0
        config_path = args.pop("config", None)
        output, formats, overwrite = args.pop("output"), args.pop("formats"), args.pop("overwrite")
        saved = {}
        if config_path is not None:
            payload = json.loads(config_path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("Config must be a JSON object.")
            saved = payload.get("config", payload)
            if not isinstance(saved, dict):
                raise ValueError("The config field must be a JSON object.")
            unknown = saved.keys() - {field.name for field in fields(Config)}
            if unknown:
                raise ValueError(f"Unknown config keys: {', '.join(sorted(unknown))}")
        if "sources" in args and "weights" not in args:
            args["weights"] = [1.0] * len(args["sources"])
        elif (
            isinstance(saved.get("sources"), (list, tuple))
            and "weights" not in saved
            and "weights" not in args
        ):
            saved["weights"] = [1.0] * len(saved["sources"])
        config = Config(**(saved | args))
        for path in render(config, output, tuple(formats), overwrite):
            print(f"Wrote {path}")
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
