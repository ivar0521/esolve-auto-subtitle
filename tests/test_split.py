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
        # 短すぎる残りは前につなげるため、最大 +4 文字まで許容する
        self.assertTrue(all(len(c.text) <= 13 for c in cues))
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

    def test_does_not_split_inside_words(self):
        # 実際の字幕で「ブ|ルビー」と単語の途中で切れていたケース
        tokens = ["オート", "ミール", "と", "イ", "チ", "ゴ", "の", "プロ", "テ", "イン", "と",
                  "ブ", "ルー", "ベ", "リー", "と", "低", "脂肪", "牛乳"]
        words = [Word(i * 0.2, i * 0.2 + 0.2, t) for i, t in enumerate(tokens)]
        cues = split_into_cues(words, max_chars=24)
        self.assertEqual(
            [c.text for c in cues],
            ["オートミールとイチゴのプロテインとブルーベリーと", "低脂肪牛乳"],
        )

    def test_prefers_natural_break_over_short_tail(self):
        # 以前は「…空いてない|けど」と「けど」だけの字幕ができていた
        words = [Word(0.0, 1.0, "寝てただけだから"), Word(1.0, 2.0, "全然お腹空いてない"),
                 Word(2.0, 2.4, "けど", segment_end=True)]
        self.assertEqual([c.text for c in split_into_cues(words, max_chars=18)],
                         ["寝てただけだから", "全然お腹空いてないけど"])

    def test_short_tail_is_merged(self):
        # 以前は「…美味しそうだ|けど」と「けど」だけの字幕ができていた
        words = [Word(0.0, 2.0, "カリカリにしたほうが美味しそうだ"), Word(2.0, 2.4, "けど", segment_end=True)]
        self.assertEqual([c.text for c in split_into_cues(words, max_chars=16)],
                         ["カリカリにしたほうが美味しそうだけど"])

    def test_okurigana_not_split(self):
        words = [Word(0.0, 0.5, "あっち"), Word(0.5, 0.8, "熱"), Word(0.8, 1.0, "い"), Word(1.0, 1.5, "熱い")]
        cues = split_into_cues(words, max_chars=4)
        self.assertNotIn("熱", [c.text for c in cues])

    def test_segment_end_splits(self):
        words = [Word(0.0, 1.0, "野菜", segment_end=True), Word(1.1, 2.0, "絶対あったほうがいい")]
        self.assertEqual([c.text for c in split_into_cues(words)], ["野菜", "絶対あったほうがいい"])

    def test_srt_format(self):
        self.assertEqual(format_timestamp(3661.5), "01:01:01,500")
        words = [Word(1.0, 2.0, "テスト")]
        self.assertEqual(to_srt(split_into_cues(words)), "1\n00:00:01,000 --> 00:00:02,000\nテスト\n")


if __name__ == "__main__":
    unittest.main()
