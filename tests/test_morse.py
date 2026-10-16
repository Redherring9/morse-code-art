import unittest

from morse_art import MORSE, Element, encode_word, layout_row, normalize_message


class MorseTests(unittest.TestCase):
    def test_alphabet_and_message_normalization(self):
        self.assertEqual(len(MORSE), 36)
        self.assertEqual(normalize_message(" i \t LOVE\n you 123 "), "I LOVE YOU 123")

    def test_invalid_messages_fail_explicitly(self):
        for message in ("", " \n", "LOVE!", "café", "ß"):
            with self.subTest(message=message), self.assertRaises(ValueError):
                normalize_message(message)

    def test_known_letters_and_standard_timing(self):
        expected = {
            "I": "..",
            "L": ".-..",
            "O": "---",
            "V": "...-",
            "E": ".",
            "Y": "-.--",
            "U": "..-",
        }
        for letter, code in expected.items():
            self.assertEqual(MORSE[letter], code)
        self.assertEqual(encode_word("I"), (Element(True, 1), Element(False, 1), Element(True, 1)))
        self.assertEqual(encode_word("ET"), (Element(True, 1), Element(False, 3), Element(True, 3)))

    def test_word_encoding_rejects_invalid_input(self):
        for word in ("", "hello", "I LOVE", "!"):
            with self.subTest(word=word), self.assertRaises(ValueError):
                encode_word(word)

    def test_row_is_justified_with_exact_ratios(self):
        row = layout_row("I LOVE YOU", 0, 300, 2, 1)
        self.assertAlmostEqual(row.unit_length * row.units, 300)
        self.assertEqual(row.elements[0], Element(True, 1))
        self.assertTrue(row.elements[-1].mark)
        self.assertIn(Element(False, 7), row.elements)
        self.assertTrue(all(e.units in (1, 3) for e in row.elements if e.mark))
        self.assertTrue(all(e.units in (1, 3, 7) for e in row.elements if not e.mark))

    def test_words_flow_across_rows_and_phrase_boundaries(self):
        message = "I LOVE YOU"
        cursor = 0
        output = []
        for length in (60, 100, 80, 50):
            row = layout_row(message, cursor, length, 2, 0.5)
            output.extend(row.words)
            cursor = row.next_word
        expected = [message.split()[i % 3] for i in range(len(output))]
        self.assertEqual(output, expected)
        self.assertEqual(cursor, len(output) % 3)

    def test_single_word_repeats_with_word_gap(self):
        row = layout_row("E", 0, 20, 1, 0.5)
        self.assertEqual(row.words, ("E", "E", "E"))
        self.assertEqual(
            row.elements,
            (
                Element(True, 1),
                Element(False, 7),
                Element(True, 1),
                Element(False, 7),
                Element(True, 1),
            ),
        )

    def test_word_may_shrink_but_not_below_minimum(self):
        row = layout_row("HELLO", 0, 30, 2, 0.5)
        self.assertEqual(row.words, ("HELLO",))
        self.assertGreaterEqual(row.unit_length, 0.5)
        with self.assertRaisesRegex(ValueError, "cannot fit"):
            layout_row("HELLO", 0, 10, 2, 1)

    def test_invalid_layout_sizes(self):
        for length in (0, -1, float("nan"), float("inf")):
            with self.subTest(length=length), self.assertRaises(ValueError):
                layout_row("I", 0, length, 1, 0.5)
        with self.assertRaises(ValueError):
            layout_row("I", 0, 100, 1, 2)


if __name__ == "__main__":
    unittest.main()
