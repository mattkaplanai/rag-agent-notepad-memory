#!/usr/bin/env bash
# Chroma'yı HTTP sunucusu olarak çalıştırır (Chroma Explorer için).
# Bağlantı: http://localhost:8000 — API Key boş bırakılabilir.
# Not: Sunucu çalışırken refund uygulamasını aynı anda çalıştırmayın (aynı DB kilitlenir).

cd "$(dirname "$0")/.."
CHROMA_PATH="${1:-./storage/chroma}"
echo "Chroma server starting — path: $CHROMA_PATH"
echo "Chroma Explorer'da URL: http://localhost:8000"
if command -v chroma &>/dev/null; then
  exec chroma run --path "$CHROMA_PATH"
else
  exec python3.10 -m chromadb run --path "$CHROMA_PATH"
fi
