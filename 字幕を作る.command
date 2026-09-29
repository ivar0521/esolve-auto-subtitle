#!/bin/bash
# 動画をドラッグ&ドロップして、同じ場所に字幕ファイル (.srt) を作ります
# (起動時に自分自身が最新版に置き換わっても動くよう、全体を関数にしてから実行する)
main() {
  cd "$(dirname "$0")" || exit 1

  if [ ! -x .venv/bin/python ]; then
    echo "先に setup.command をダブルクリックして準備してください。"
    read -r -p "Enter キーで閉じます"
    exit 1
  fi

  ./.venv/bin/python update.py

  echo ""
  echo "字幕を付けたい動画ファイルを、この画面にドラッグ&ドロップして Enter を押してください。"
  echo "(複数まとめてもOK)"
  read -r -p "> " input
  # ドラッグ&ドロップで入る「\ 」などのエスケープを解釈してファイル名に戻す
  eval "set -- $input"

  echo ""
  echo "精度を選んでください: 1=高精度(既定・時間がかかる)  2=速い"
  read -r -p "> " choice
  model="large-v3-turbo"
  [ "$choice" = "2" ] && model="small"

  echo ""
  echo "それでも声が抜ける場合だけ 3 を選んでください: 3=全部の音を文字起こしする (BGM だけの所に変な字幕が出ることがあります)"
  echo "(普段はそのまま Enter)"
  read -r -p "> " vad
  extra=()
  [ "$vad" = "3" ] && extra=(--no-vad)

  if [ ! -s "APIキー.txt" ]; then
    echo ""
    echo "AI で字幕を自然に直す場合は、Anthropic の API キーを貼り付けて Enter してください。"
    echo "(使わない場合はそのまま Enter)"
    read -r -p "> " key
    [ -n "$key" ] && printf '%s\n' "$key" > "APIキー.txt"
  fi
  if [ -s "APIキー.txt" ]; then
    echo ""
    echo "動画の内容を一言で入力してください (AI のヒントになります。例: 朝ごはんと夜ごはんのダイエット vlog)"
    echo "(空のまま Enter でもOK)"
    read -r -p "> " about
    extra+=(--about "$about")
  fi

  ./.venv/bin/python auto_subtitle.py --model "$model" "${extra[@]}" "$@"
  echo ""
  read -r -p "終わりました。Enter キーで閉じます"
}
main "$@"
exit
