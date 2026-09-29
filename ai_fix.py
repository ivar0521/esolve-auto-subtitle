"""Claude で字幕の聞き間違い・不自然な区切りを直す。

API キーは環境変数 ANTHROPIC_API_KEY か、このフォルダの「APIキー.txt」から読む。
直した字幕に出てきた固有名詞などは「覚えた単語.txt」に貯めて、次回以降のヒントにする。
"""

from __future__ import annotations

import json
import os
from pathlib import Path

HERE = Path(__file__).parent
KEY_FILE = HERE / "APIキー.txt"
VOCAB_FILE = HERE / "覚えた単語.txt"
MODEL = "claude-opus-5-5"
BATCH = 80  # 1 回に送る字幕の数 (長い動画は分けて送る)
MAX_VOCAB = 500

SYSTEM = """あなたは日本語の動画字幕の校正者です。音声認識 (Whisper) が作った vlog の字幕を、視聴者が読んで自然な字幕に直します。

字幕は id・表示時間・テキストの一覧で渡されます。表示時間は変えられないので、id ごとに直したテキストを返してください。渡された id はすべて返します。

直すもの:
- 聞き間違い。存在しない語や文脈に合わない語は、文脈上いちばん自然な実在の語に直す (例: ブルビー→ブルーベリー、GPD→GPT、焼くライダー→エアフライヤー)。
- 隣り合う字幕の境目で分かれてしまった単語は、正しい側に文字を移す (例:「全然お」「腹空いてない」→「全然」「お腹空いてない」、「生姜とニンニ」「クちょっと」→「生姜とニンニク」「ちょっと」)。
- 途中で切れた語の補完、ゴミ文字や同じ語の不要な繰り返しの削除。
- unsure: true の字幕は聞き取りに自信がない部分です。前後の文脈から話者が言っていそうな語を推測して直してください。雑音や意味のない音だと判断したら空文字にして削除します。

守ること:
- 話し言葉の口調 (「うめぇ」「食べらんない」など) はそのまま残す。
- 言っていない内容を付け足さない。文全体を言い換えない。
- 字幕の末尾に「。」は付けない。1 つの字幕は短いままにする。

あわせて、直した字幕に出てきた固有名詞・商品名・料理名・食材名など、次回の聞き取りのヒントになる語を vocabulary に入れてください。"""

SCHEMA = {
    "type": "object",
    "properties": {
        "cues": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"id": {"type": "integer"}, "text": {"type": "string"}},
                "required": ["id", "text"],
                "additionalProperties": False,
            },
        },
        "vocabulary": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["cues", "vocabulary"],
    "additionalProperties": False,
}


def load_api_key() -> str | None:
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not key and KEY_FILE.is_file():
        key = KEY_FILE.read_text(encoding="utf-8").strip()
    return key or None


def load_vocab() -> list[str]:
    if not VOCAB_FILE.is_file():
        return []
    lines = VOCAB_FILE.read_text(encoding="utf-8").splitlines()
    return [w.strip() for w in lines if w.strip() and not w.startswith("#")]


def save_vocab(new_words: list[str]) -> list[str]:
    """新しく出てきた単語だけを追記し、追加した単語を返す。"""
    known = load_vocab()
    added = [w for w in dict.fromkeys(w.strip() for w in new_words) if w and w not in known]
    words = (known + added)[-MAX_VOCAB:]
    header = "# AI が字幕を直したときに覚えた単語です。自由に書き足し・削除できます。\n"
    VOCAB_FILE.write_text(header + "\n".join(words) + "\n", encoding="utf-8")
    return added


def _request(client, items: list[dict], about: str, vocab: list[str], before: list[str]) -> dict | None:
    hints = []
    if about:
        hints.append(f"動画の内容: {about}")
    if vocab:
        hints.append("この話者の動画によく出てくる単語: " + "、".join(vocab))
    if before:
        hints.append("直前の字幕 (参考。返さなくてよい): " + " / ".join(before))
    content = "\n".join(hints + ["字幕:", json.dumps(items, ensure_ascii=False)])

    response = client.beta.messages.create(
        model=MODEL,
        max_tokens=16000,
        # 安全判定で断られたときは、別のモデルで自動的にやり直す
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        output_config={"effort": "medium", "format": {"type": "json_schema", "schema": SCHEMA}},
        system=SYSTEM,
        messages=[{"role": "user", "content": content}],
    )
    if response.stop_reason in ("refusal", "max_tokens"):
        print(f"  ⚠ AI 修正を一部スキップしました (理由: {response.stop_reason})")
        return None
    text = next((b.text for b in response.content if b.type == "text"), "")
    return json.loads(text)


def ai_fix(cues: list, about: str = "") -> list:
    """字幕 (Cue のリスト) を Claude で直して返す。失敗したら元の字幕を返す。"""
    key = load_api_key()
    if not key or not cues:
        return cues
    import anthropic

    client = anthropic.Anthropic(api_key=key)
    vocab = load_vocab()
    fixed_text: dict[int, str] = {}
    new_vocab: list[str] = []
    print(f"  AI ({MODEL}) で字幕を校正中…")
    try:
        for start in range(0, len(cues), BATCH):
            items = [
                {"id": i, "start": round(c.start, 2), "end": round(c.end, 2), "text": c.text, "unsure": c.unsure}
                for i, c in enumerate(cues[start : start + BATCH], start=start)
            ]
            before = [c.text for c in cues[max(0, start - 5) : start]]
            result = _request(client, items, about, vocab, before)
            if result:
                fixed_text.update({c["id"]: c["text"].strip() for c in result["cues"]})
                new_vocab += result["vocabulary"]
    except anthropic.AuthenticationError:
        print("  ⚠ API キーが正しくありません。APIキー.txt を確認してください (AI 修正なしで保存します)")
        return cues
    except (anthropic.APIConnectionError, anthropic.APIStatusError) as e:
        print(f"  ⚠ AI に接続できませんでした ({e}) — AI 修正なしで保存します")
        return cues

    result_cues = []
    changed = 0
    for i, cue in enumerate(cues):
        text = fixed_text.get(i, cue.text)
        if text:
            changed += text != cue.text
            cue.text = text
            result_cues.append(cue)
    added = save_vocab(new_vocab)
    print(f"  AI 校正: {changed} か所を修正、{len(cues) - len(result_cues)} 件を削除")
    if added:
        print(f"  覚えた単語を追加: {'、'.join(added)}")
    return result_cues
