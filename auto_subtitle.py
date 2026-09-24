#!/usr/bin/env python3
"""動画・音声ファイルから DaVinci Resolve 用の字幕ファイル (.srt) を自動で作るツール。

音声認識には faster-whisper (Whisper) を使い、すべて手元のパソコン上で処理します。
使い方:
    python auto_subtitle.py 動画.mp4 [動画2.mov ...] [--model small] [--max-chars 18]
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

# 文の区切りとみなす文字 (ここで字幕を切る)
SENTENCE_END = tuple("。！？!?")
# 字幕の末尾から取り除く文字 (日本語字幕では句点を付けないのが一般的)
TRAILING_STRIP = "。、,."


@dataclass
class Word:
    start: float
    end: float
    text: str


@dataclass
class Cue:
    start: float
    end: float
    text: str


def split_into_cues(
    words: list[Word],
    max_chars: int = 18,
    max_duration: float = 6.0,
    max_gap: float = 0.6,
    strip_punctuation: bool = True,
) -> list[Cue]:
    """単語ごとのタイムスタンプを、読みやすい長さの字幕に分割する。

    次のいずれかで字幕を区切る:
    - 文字数が max_chars を超えそう
    - 字幕の長さが max_duration 秒を超えそう
    - 前の単語から max_gap 秒以上の無音がある
    - 「。」「？」など文の終わり
    """
    cues: list[Cue] = []
    current: list[Word] = []

    def text_of(ws: list[Word]) -> str:
        return "".join(w.text for w in ws).strip()

    def flush() -> None:
        if not current:
            return
        text = text_of(current)
        if strip_punctuation:
            text = text.rstrip(TRAILING_STRIP).strip()
        if text:
            cues.append(Cue(current[0].start, current[-1].end, text))
        current.clear()

    for word in words:
        if not word.text.strip():
            continue
        if current:
            too_long = len(text_of(current + [word])) > max_chars
            too_slow = word.end - current[0].start > max_duration
            gap = word.start - current[-1].end > max_gap
            if too_long or too_slow or gap:
                flush()
        current.append(word)
        if word.text.strip().endswith(SENTENCE_END):
            flush()
    flush()

    # 字幕が一瞬で消えないよう、最低表示時間を確保する (次の字幕とは重ねない)
    min_duration = 0.8
    for i, cue in enumerate(cues):
        limit = cues[i + 1].start if i + 1 < len(cues) else cue.end + min_duration
        if cue.end - cue.start < min_duration:
            cue.end = min(cue.start + min_duration, limit)
    return cues


def format_timestamp(seconds: float) -> str:
    ms = max(0, round(seconds * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def to_srt(cues: list[Cue]) -> str:
    blocks = [
        f"{i}\n{format_timestamp(c.start)} --> {format_timestamp(c.end)}\n{c.text}\n"
        for i, c in enumerate(cues, start=1)
    ]
    return "\n".join(blocks)


def transcribe(path: Path, model, language: str | None) -> list[Word]:
    segments, info = model.transcribe(
        str(path),
        language=language,
        word_timestamps=True,
        vad_filter=True,  # 無音部分を飛ばし、無音中の誤認識を防ぐ
        condition_on_previous_text=False,  # 同じ文の繰り返し出力を防ぐ
    )
    print(f"  言語: {info.language}  長さ: {info.duration:.0f}秒")
    words: list[Word] = []
    for seg in segments:
        print(f"  [{format_timestamp(seg.start)}] {seg.text.strip()}")
        for w in seg.words or []:
            words.append(Word(w.start, w.end, w.word))
    return words


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="動画から字幕ファイル (.srt) を自動作成")
    parser.add_argument("files", nargs="+", type=Path, help="動画または音声ファイル")
    parser.add_argument(
        "--model",
        default="large-v3-turbo",
        help="音声認識モデル: small(速い) / medium / large-v3-turbo(既定・高精度)",
    )
    parser.add_argument("--language", default="ja", help="話している言語 (既定: ja)。auto で自動判定")
    parser.add_argument("--max-chars", type=int, default=18, help="1つの字幕の最大文字数 (既定: 18)")
    parser.add_argument("--keep-punctuation", action="store_true", help="字幕末尾の「。」を残す")
    args = parser.parse_args(argv)

    missing = [f for f in args.files if not f.is_file()]
    if missing:
        for f in missing:
            print(f"ファイルが見つかりません: {f}", file=sys.stderr)
        return 1

    from faster_whisper import WhisperModel

    print(f"モデル「{args.model}」を読み込み中… (初回はダウンロードに数分かかります)")
    model = WhisperModel(args.model, device="auto", compute_type="int8")
    language = None if args.language == "auto" else args.language

    for path in args.files:
        print(f"\n▶ {path.name} を文字起こし中…")
        words = transcribe(path, model, language)
        cues = split_into_cues(
            words,
            max_chars=args.max_chars,
            strip_punctuation=not args.keep_punctuation,
        )
        out = path.with_suffix(".srt")
        out.write_text(to_srt(cues), encoding="utf-8")
        print(f"✅ 字幕 {len(cues)} 件を保存しました: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
