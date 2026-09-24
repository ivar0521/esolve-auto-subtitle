import unittest

from auto_subtitle import Word, format_timestamp, split_into_cues, to_srt


class SplitTest(unittest.TestCase):
    def test_splits_on_sentence_end_and_strips_period(self):
        words = [Word(0.0, 0.5, "こんにちは"), Word(0.5, 0.6, "。"), Word(0.7, 1.5, "今日は")]
        cues = split_into_cues(words)
        self.assertEqual([c.text for c in cues], ["こんにちは", "今日は"])

    def test_splits_when_too_long(self):
        words = [Word(i * 0.2, i * 0.2 + 0.2, "あいう") for i in range(10)]
        cues = split_into_cues(words, max_chars=9)
        self.assertTrue(all(len(c.text) <= 9 for c in cues))
        self.assertEqual("".join(c.text for c in cues), "あいう" * 10)

    def test_splits_on_silence(self):
        words = [Word(0.0, 1.0, "前半"), Word(3.0, 4.0, "後半")]
        self.assertEqual([c.text for c in split_into_cues(words)], ["前半", "後半"])

    def test_english_spacing(self):
        words = [Word(0.0, 0.3, " Hello"), Word(0.3, 0.6, " world.")]
        self.assertEqual(split_into_cues(words, max_chars=40)[0].text, "Hello world")

    def test_min_duration_does_not_overlap_next(self):
        words = [Word(0.0, 0.1, "あ"), Word(0.1, 0.2, "。"), Word(0.5, 1.5, "い")]
        cues = split_into_cues(words)
        self.assertLessEqual(cues[0].end, cues[1].start)

    def test_srt_format(self):
        self.assertEqual(format_timestamp(3661.5), "01:01:01,500")
        words = [Word(1.0, 2.0, "テスト")]
        self.assertEqual(to_srt(split_into_cues(words)), "1\n00:00:01,000 --> 00:00:02,000\nテスト\n")


if __name__ == "__main__":
    unittest.main()
