#!/bin/bash
# 動画をドラッグ&ドロップして、同じ場所に字幕ファイル (.srt) を作ります
cd "$(dirname "$0")" || exit 1

if [ ! -x .venv/bin/python ]; then
  echo "先に setup.command をダブルクリックして準備してください。"
  read -r -p "Enter キーで閉じます"
  exit 1
fi

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

./.venv/bin/python auto_subtitle.py --model "$model" "$@"
echo ""
read -r -p "終わりました。Enter キーで閉じます"
