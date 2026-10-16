import hashlib
import io
import json
import tempfile
import unittest
import xml.etree.ElementTree as ET
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import numpy as np
from PIL import Image

from morse_art import (
    Config,
    Element,
    Row,
    Waveform,
    build_figure,
    canvas_geometry,
    generate_waveforms,
    layout_row,
    load_profile,
    main,
    morse_segments,
    render,
)


class GeometryTests(unittest.TestCase):
    def setUp(self):
        self.config = Config(lines=6, samples=512, dpi=72)
        self.profiles = [load_profile(key) for key in self.config.sources]

    def test_seed_is_reproducible_and_changes_the_signal(self):
        first = generate_waveforms(self.config, self.profiles)
        second = generate_waveforms(self.config, self.profiles)
        changed = generate_waveforms(replace(self.config, seed=1920), self.profiles)
        for a, b in zip(first, second, strict=True):
            np.testing.assert_array_equal(a.y, b.y)
        self.assertFalse(np.array_equal(first[0].y, changed[0].y))

    def test_waveforms_fit_margins_have_quiet_edges_and_stack_back_to_front(self):
        waves = generate_waveforms(self.config, self.profiles)
        _, bottom, spacing = canvas_geometry(self.config)
        margin = self.config.margin * 72
        for index, wave in enumerate(waves):
            baseline = bottom + (self.config.lines - index - 1) * spacing
            self.assertAlmostEqual(wave.y[0], baseline)
            self.assertAlmostEqual(wave.y[-1], baseline)
            self.assertGreaterEqual(wave.y.min(), margin)
            self.assertLessEqual(wave.y.max(), self.config.height * 72 - margin)
            self.assertLessEqual(wave.y.max() - baseline, self.config.peak_height + 1e-9)
            self.assertGreaterEqual(wave.x.min(), margin)
            self.assertLessEqual(wave.x.max(), self.config.width * 72 - margin)
            self.assertTrue(np.all(np.diff(wave.x) > 0))
        self.assertGreater(waves[0].y[0], waves[-1].y[0])

    def test_zero_height_makes_flat_lines(self):
        waves = generate_waveforms(replace(self.config, peak_height=0), self.profiles)
        self.assertTrue(all(np.ptp(wave.y) == 0 for wave in waves))

    def test_single_row_and_explicit_spacing(self):
        single = replace(self.config, lines=1)
        self.assertEqual(canvas_geometry(single)[2], 0)
        self.assertEqual(len(generate_waveforms(single, self.profiles)), 1)
        self.assertEqual(canvas_geometry(replace(self.config, line_spacing=8))[2], 8)

    def test_morse_lengths_follow_arc_not_horizontal_distance(self):
        x = np.linspace(0, 100, 1001)
        wave = Waveform(x, 30 * np.sin(x / 10))
        row = layout_row("I LOVE YOU", 0, float(wave.arc[-1]), 1.5, 0.5)
        segments = morse_segments(wave, row)
        marks = [element for element in row.elements if element.mark]
        self.assertEqual(len(segments), len(marks))
        for segment, element in zip(segments, marks, strict=True):
            length = np.hypot(np.diff(segment[:, 0]), np.diff(segment[:, 1])).sum()
            self.assertAlmostEqual(length, element.units * row.unit_length, places=9)
        np.testing.assert_allclose(segments[0][0], [wave.x[0], wave.y[0]])
        np.testing.assert_allclose(segments[-1][-1], [wave.x[-1], wave.y[-1]])
        self.assertTrue(any(abs(s[-1, 0] - s[0, 0]) < row.unit_length / 2 for s in segments))
        with self.assertRaisesRegex(ValueError, "justified"):
            morse_segments(wave, replace(row, unit_length=2 * row.unit_length))

    def test_foreground_masks_hide_background_even_inside_morse_gaps(self):
        config = Config(
            width=4, height=4, margin=0.25, dpi=144, stroke_width=3, min_unit=3, unit=5, lines=2
        )
        back = Waveform(np.array([36.0, 252.0]), np.array([120.0, 120.0]))
        front = Waveform(
            np.array([36.0, 80.0, 100.0, 180.0, 200.0, 252.0]),
            np.array([100.0, 100.0, 180.0, 180.0, 100.0, 100.0]),
        )
        back_row = Row(("T",), (Element(True, 3),), float(back.arc[-1]) / 3, 0)
        front_row = Row(
            ("T", "T"),
            (Element(True, 3), Element(False, 7), Element(True, 3)),
            float(front.arc[-1]) / 13,
            0,
        )
        figure = build_figure(config, [back, front], [back_row, front_row])
        figure.canvas.draw()
        image = np.asarray(figure.canvas.buffer_rgba())

        def pixel(x, y):
            return image[round((config.height * 72 - y) * 2), round(x * 2), :3]

        np.testing.assert_array_equal(pixel(140, 120), [17, 17, 17])
        np.testing.assert_array_equal(pixel(140, 180), [17, 17, 17])
        self.assertTrue(np.all(pixel(60, 120) > 200))
        figure.clear()

    def test_invalid_configurations_fail_explicitly(self):
        cases = (
            {"message": "HELLO!"},
            {"message": 123},
            {"lines": 0},
            {"lines": True},
            {"seed": -1},
            {"dpi": 0},
            {"samples": 20},
            {"margin": 5},
            {"margin": "1"},
            {"peak_height": 1000},
            {"width": float("nan")},
            {"width": 40, "height": 40, "dpi": 1200},
            {"stroke_width": 0},
            {"stroke_width": 1},
            {"min_unit": 2},
            {"coherence": 1},
            {"roughness": -1},
            {"drift": 1},
            {"signal_width": 0},
            {"line_spacing": 1000},
            {"line_spacing": float("inf")},
            {"foreground": "not-a-color"},
            {"background": "none"},
            {"foreground": "#111111"},
            {"weights": (0, 0)},
            {"weights": (-1, 2)},
            {"weights": (1,)},
            {"weights": (float("nan"), 1)},
            {"sources": ()},
            {"sources": ("missing",)},
            {"sources": 123},
        )
        for changes in cases:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                replace(self.config, **changes).validate()


class ExportTests(unittest.TestCase):
    def setUp(self):
        self.config = Config(
            width=4, height=5, margin=0.4, peak_height=30, lines=3, samples=256, dpi=72
        )

    def test_vector_png_metadata_and_replay_are_consistent_and_offline(self):
        with (
            tempfile.TemporaryDirectory() as directory,
            patch(
                "socket.create_connection", side_effect=AssertionError("Rendering must be offline")
            ),
        ):
            output = Path(directory) / "art"
            paths = render(self.config, output)
            self.assertEqual({p.suffix for p in paths}, {".svg", ".png", ".json"})
            metadata = json.loads(output.with_suffix(".json").read_text())
            self.assertEqual(len(metadata["rows"]), 3)
            self.assertEqual(metadata["config"]["message"], "I LOVE YOU")
            self.assertIn("not a measured sequence", metadata["description"])
            for suffix in ("svg", "png"):
                digest = hashlib.sha256(output.with_suffix(f".{suffix}").read_bytes()).hexdigest()
                self.assertEqual(metadata["outputs"][suffix]["sha256"], digest)
            with Image.open(output.with_suffix(".png")) as image:
                self.assertEqual(image.size, (288, 360))
                self.assertAlmostEqual(image.info["dpi"][0], 72, places=1)
                self.assertEqual(image.getpixel((0, 0)), (17, 17, 17, 255))
                png_metadata = json.loads(image.info["Description"])
                self.assertEqual(png_metadata["config"], metadata["config"])
                self.assertIn("CC BY 4.0", image.info["Description"])
            root = ET.parse(output.with_suffix(".svg")).getroot()
            svg = {"svg": "http://www.w3.org/2000/svg"}
            self.assertEqual(root.attrib["width"], "288pt")
            self.assertEqual(root.attrib["height"], "360pt")
            self.assertFalse(root.findall(".//svg:image", svg))
            self.assertFalse(root.findall(".//svg:text", svg))
            ids = [node.attrib.get("id", "") for node in root.iter()]
            self.assertEqual(sum(i.startswith("morse-row-") for i in ids), 3)
            self.assertEqual(sum(i.startswith("occlusion-row-") for i in ids), 3)
            replay = Path(directory) / "replay"
            with redirect_stdout(io.StringIO()):
                self.assertEqual(
                    main(["--config", str(output.with_suffix(".json")), "--output", str(replay)]), 0
                )
            for suffix in ("svg", "png"):
                self.assertEqual(
                    output.with_suffix(f".{suffix}").read_bytes(),
                    replay.with_suffix(f".{suffix}").read_bytes(),
                )
            self.assertFalse(list(Path(directory).glob(".morse-art-*")))

    def test_overwrite_is_explicit_and_failure_leaves_existing_files_untouched(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "art"
            render(self.config, output, ("svg",))
            original = output.with_suffix(".svg").read_bytes()
            with self.assertRaises(FileExistsError):
                render(self.config, output)
            self.assertEqual(output.with_suffix(".svg").read_bytes(), original)
            render(self.config, output, ("svg",), overwrite=True)
            self.assertEqual(output.with_suffix(".svg").read_bytes(), original)
            with self.assertRaises(ValueError):
                render(self.config, output, ("svg", "svg"), overwrite=True)
            with patch("morse_art.Figure.savefig", side_effect=OSError("Disk full")):
                with self.assertRaisesRegex(OSError, "Disk full"):
                    render(self.config, output, overwrite=True)
            self.assertEqual(output.with_suffix(".svg").read_bytes(), original)
            self.assertFalse(output.with_suffix(".png").exists())
            self.assertFalse(list(Path(directory).glob(".morse-art-*")))

    def test_cli_custom_source_uses_equal_weights(self):
        with tempfile.TemporaryDirectory() as directory, redirect_stdout(io.StringIO()):
            output = Path(directory) / "custom"
            main(
                [
                    "--sources",
                    "b0329-hba",
                    "--lines",
                    "1",
                    "--dpi",
                    "72",
                    "--formats",
                    "svg",
                    "--message",
                    "hello 123",
                    "--output",
                    str(output),
                ]
            )
            metadata = json.loads(output.with_suffix(".json").read_text())
            self.assertEqual(metadata["config"]["weights"], [1.0])
            self.assertEqual(metadata["config"]["message"], "HELLO 123")
            self.assertEqual(metadata["sources"][0]["pulsar"], "J0332+5434")

    def test_cli_invalid_configs_produce_usage_errors_not_tracebacks(self):
        cases = (
            [],
            {"config": None},
            {"unknown": 1},
            {"sources": 3},
            {"lines": True},
            {"weights": "wrong"},
            {"message": "HI!"},
        )
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "bad.json"
            for data in cases:
                config.write_text(json.dumps(data))
                with self.subTest(data=data), redirect_stderr(io.StringIO()) as errors:
                    with self.assertRaises(SystemExit) as raised:
                        main(["--config", str(config)])
                    self.assertEqual(raised.exception.code, 2)
                    self.assertIn("error:", errors.getvalue())
                    self.assertNotIn("Traceback", errors.getvalue())


if __name__ == "__main__":
    unittest.main()
