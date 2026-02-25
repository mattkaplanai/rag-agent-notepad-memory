# Bu projeyi GitHub'da ayrı repo olarak yayınlama

Proje zaten yerel git repo ve ilk commit atıldı. Aşağıdaki adımlarla GitHub'da **yeni bir repo** oluşturup kodu oraya gönderebilirsin.

---

## 1. GitHub'da yeni repo oluştur

1. **github.com** → giriş yap (hesap: **sftwaredvlp**).
2. Sol tarafta **"Top repositories"** altında yeşil **"New"** butonuna tıkla (veya sağ üst **+** → **New repository**).
3. **Repository name:** İstediğin isim, örn: `rag-agent-notepad-memory` veya `project-with-ergun`.
4. **Description (isteğe bağlı):** Örn: "RAG Agent with notepad, long/short memory and tools (LangChain, Gradio)".
5. **Public** seç.
6. **"Add a README file"**, **".gitignore"**, **"license"** ekleme (projede zaten var).
7. **Create repository** ile repo'yu oluştur.

---

## 2. Yerel projeyi GitHub repo'ya bağla ve push et

GitHub repo oluşturulduktan sonra sayfada gösterilen **repo URL**'ini kullan. Örnek:

- HTTPS: `https://github.com/sftwaredvlp/rag-agent-notepad-memory.git`
- SSH:   `git@github.com:sftwaredvlp/rag-agent-notepad-memory.git`

Terminalde proje klasöründe şunları çalıştır (**REPO_ADI** yerine kendi repo adını yaz):

```bash
cd "/Users/mehmetkaymak/Desktop/Project with Ergun"

# GitHub'daki yeni repoyu remote olarak ekle (REPO_ADI = örn. rag-agent-notepad-memory)
git remote add origin https://github.com/sftwaredvlp/REPO_ADI.git

# Ana branch'i gönder
git push -u origin main
```

Örnek (repo adı `rag-agent-notepad-memory` ise):

```bash
git remote add origin https://github.com/sftwaredvlp/rag-agent-notepad-memory.git
git push -u origin main
```

İlk push’ta GitHub kullanıcı adı ve şifre/token istenebilir. Şifre yerine **Personal Access Token (PAT)** kullanman gerekir (Settings → Developer settings → Personal access tokens).

---

## 3. Sonraki güncellemeler

Değişiklikleri göndermek için:

```bash
git add -A
git commit -m "Kısa açıklama"
git push
```

---

## Commit’e girmeyenler (.gitignore)

- `.env` (API anahtarları)
- `venv/`
- `storage/` (indeks)
- `notepad.txt`, `long_memory.json` (yerel not/bellek)

Bu dosyalar GitHub’a **gönderilmez**; güvenlik ve taşınabilirlik için doğru.
