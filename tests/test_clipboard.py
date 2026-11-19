import unittest

from noteboard.clipboard import NulFramer


class NulFramerTest(unittest.TestCase):
    def setUp(self):
        self.framer = NulFramer()

    def test_single_frame(self):
        self.assertEqual(self.framer.feed(b"hello\0"), ["hello"])

    def test_multiple_frames_in_one_chunk(self):
        self.assertEqual(self.framer.feed(b"a\0b\nc\0"), ["a", "b\nc"])

    def test_frame_split_across_chunks(self):
        self.assertEqual(self.framer.feed(b"hel"), [])
        self.assertEqual(self.framer.feed(b"lo\0"), ["hello"])

    def test_multibyte_split_across_chunks(self):
        data = "héllo €".encode("utf-8") + b"\0"
        cut = data.index("€".encode("utf-8")) + 1  # inside the 3-byte €
        self.assertEqual(self.framer.feed(data[:cut]), [])
        self.assertEqual(self.framer.feed(data[cut:]), ["héllo €"])

    def test_trailing_partial_frame_retained(self):
        self.assertEqual(self.framer.feed(b"one\0tw"), ["one"])
        self.assertEqual(self.framer.feed(b"o\0"), ["two"])

    def test_invalid_utf8_replaced(self):
        self.assertEqual(self.framer.feed(b"a\xffb\0"), ["a�b"])


if __name__ == "__main__":
    unittest.main()
