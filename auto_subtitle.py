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
    segment_end: bool = False  # Whisper が区切った発話のまとまりの最後の単語


@dataclass
class Cue:
    start: float
    end: float
    text: str
    cut: bool = False  # 長すぎて途中で切った字幕 (続きが次の字幕にある)


def char_type(c: str) -> str:
    if c in "、，,":
        return "comma"
    if c in SENTENCE_END:
        return "end"
    o = ord(c)
    if 0x3040 <= o <= 0x309F:
        return "hira"
    if 0x30A0 <= o <= 0x30FF:
        return "kata"
    if 0x4E00 <= o <= 0x9FFF or c in "々〆":
        return "kanji"
    if c.isalnum():
        return "alnum"
    return "other"


def boundary_score(left: str, right: str) -> int:
    """left の直後 (= right の直前) で字幕を切ったときの自然さ。高いほど良い。

    Whisper の単語は日本語だと単語の途中で分かれていることが多いので、
    文字の種類の変わり目から「言葉の切れ目らしさ」を推定する。
    """
    left = left.rstrip()
    if not left or not right.strip():
        return 0
    if right[0].isspace():  # 英語など、空白で区切られる言語
        return 3
    a, b = char_type(left[-1]), char_type(right.lstrip()[0])
    if a in ("end", "comma"):
        return 4
    if a == "hira" and b in ("kanji", "kata", "alnum"):  # 「と|イチゴ」助詞の後
        return 3
    if a == "hira" and b == "hira":  # 「ない|けど」
        return 1
    if a != b and {a, b} <= {"kanji", "kata", "alnum"}:  # 「ベリー|低脂肪」
        return 1
    # 「ブ|ルビー」「熱|い」「米|が」など、単語の途中の可能性が高い
    return 0


def split_into_cues(
    words: list[Word],
    max_chars: int = 24,
    max_duration: float = 7.0,
    max_gap: float = 0.6,
    strip_punctuation: bool = True,
) -> list[Cue]:
    """単語ごとのタイムスタンプを、読みやすい長さの字幕に分割する。

    次のいずれかで字幕を区切る:
    - 「。」「？」など文の終わり、発話のまとまりの終わり
    - 前の単語から max_gap 秒以上の無音がある
    - 文字数が max_chars を超えそう / 長さが max_duration 秒を超えそう
      → このときは、単語の途中を避けて一番自然な位置で切る
    """
    cues: list[Cue] = []
    current: list[Word] = []

    def text_of(ws: list[Word]) -> str:
        return "".join(w.text for w in ws).strip()

    def emit(ws: list[Word], cut: bool = False) -> None:
        text = text_of(ws)
        if strip_punctuation:
            text = text.rstrip(TRAILING_STRIP).strip()
        if text:
            cues.append(Cue(ws[0].start, ws[-1].end, text, cut))

    def flush() -> None:
        if current:
            emit(current)
        current.clear()

    def split_best(next_word: Word) -> None:
        """current を自然な位置で前後に分け、前半だけを字幕にする。"""
        followers = current[1:] + [next_word]
        best = max(
            range(1, len(current) + 1),
            key=lambda i: (boundary_score(text_of(current[:i]), followers[i - 1].text), i),
        )
        emit(current[:best], cut=True)
        del current[:best]

    for word in words:
        if not word.text.strip():
            continue
        if current and word.start - current[-1].end > max_gap:
            flush()
        while current and (
            len(text_of(current + [word])) > max_chars
            or word.end - current[0].start > max_duration
        ):
            split_best(word)
        current.append(word)
        if word.segment_end or word.text.strip().endswith(SENTENCE_END):
            flush()
    flush()

    # 長さで切った結果「けど」「とか」だけになった短すぎる字幕は、直前の字幕につなげる
    merged: list[Cue] = []
    for cue in cues:
        prev = merged[-1] if merged else None
        if (
            prev
            and prev.cut
            and len(cue.text) <= 3
            and cue.start - prev.end <= 0.3
            and len(prev.text) + len(cue.text) <= max_chars + 4
        ):
            sep = " " if prev.text[-1].isascii() and cue.text[0].isascii() else ""
            prev.text += sep + cue.text
            prev.end = cue.end
            prev.cut = cue.cut
        else:
            merged.append(cue)
    cues = merged

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


def transcribe(path: Path, model, language: str | None, use_vad: bool = True) -> list[Word]:
    segments, info = model.transcribe(
        str(path),
        language=language,
        word_timestamps=True,
        # 無音部分を飛ばし、無音中の誤認識を防ぐ。ぼそっと話す声や BGM に重なった声を
        # 落とさないよう、声とみなす基準 (既定 0.5) を大きく下げ、前後の余白も広げている
        vad_filter=use_vad,
        vad_parameters={"threshold": 0.2, "speech_pad_ms": 600},
        condition_on_previous_text=False,  # 同じ文の繰り返し出力を防ぐ
    )
    print(f"  言語: {info.language}  長さ: {info.duration:.0f}秒")
    words: list[Word] = []
    for seg in segments:
        print(f"  [{format_timestamp(seg.start)}] {seg.text.strip()}")
        seg_words = [Word(w.start, w.end, w.word) for w in seg.words or []]
        if seg_words:
            seg_words[-1].segment_end = True
        words.extend(seg_words)
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
    parser.add_argument("--max-chars", type=int, default=24, help="1つの字幕の最大文字数 (既定: 24)")
    parser.add_argument("--keep-punctuation", action="store_true", help="字幕末尾の「。」を残す")
    parser.add_argument(
        "--no-vad",
        action="store_true",
        help="無音の自動スキップを止める (声が抜けるとき用。BGM だけの部分で誤字幕が出やすくなる)",
    )
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
        words = transcribe(path, model, language, use_vad=not args.no_vad)
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
