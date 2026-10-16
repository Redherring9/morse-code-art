#!/usr/bin/env python3
"""Render depth-stacked, justified Morse waveforms from real pulsar profiles."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
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


if __name__ == "__main__":
    raise SystemExit("Rendering CLI will be added at the next implementation checkpoint.")
