#!/usr/bin/env python3
"""Render depth-stacked, justified Morse waveforms from real pulsar profiles."""

from __future__ import annotations

import math
from dataclasses import dataclass

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
