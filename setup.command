#!/bin/bash
# 初回だけ実行: 字幕ツールに必要なものをインストールします
cd "$(dirname "$0")" || exit 1

if ! command -v python3 >/dev/null 2>&1; then
  echo "Python が見つかりません。https://www.python.org/downloads/ からインストールしてから、もう一度実行してください。"
  read -r -p "Enter キーで閉じます"
  exit 1
fi

echo "準備中です… (数分かかります)"
python3 -m venv .venv && ./.venv/bin/pip install --upgrade pip -q && ./.venv/bin/pip install -r requirements.txt -q
if [ $? -eq 0 ]; then
  echo ""
  echo "✅ 準備完了！ 次からは「字幕を作る.command」をダブルクリックしてください。"
else
  echo ""
  echo "❌ インストールに失敗しました。この画面の文字をコピーして相談してください。"
fi
read -r -p "Enter キーで閉じます"
