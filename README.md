# RAG Projesi: Doküman Tabanlı Soru-Cevap

Bu proje, **bilgiler** klasöründeki PDF, Word ve metin dosyalarını kullanarak soru-cevap yapan bir RAG (Retrieval-Augmented Generation) uygulamasıdır.

## Çalışma Mantığı

1. **Giriş:** Kullanıcı Gradio arayüzündeki soru kutusuna sorusunu yazar.
2. **Arama:** LlamaIndex, dosyalardaki ilgili parçaları vektör indeksi üzerinden bulur.
3. **Birleştirme:** LangChain, soruyu ve bulunan metni OpenAI’a ileten zinciri yönetir.
4. **Sonuç:** OpenAI cevabı üretir ve Gradio ekranındaki cevap alanında gösterilir.

## Kurulum

### 1. Sanal ortam (önerilir)

```bash
python3 -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
```

### 2. Bağımlılıkları yükle

```bash
pip install -r requirements.txt
```

### 3. OpenAI API anahtarı

- [OpenAI API Keys](https://platform.openai.com/api-keys) sayfasından anahtar alın.
- Proje klasöründe `.env` dosyası oluşturun (`.env.example` dosyası örnektir):

```bash
cp .env.example .env
```

- `.env` içine anahtarınızı yazın:

```
OPENAI_API_KEY=sk-proj-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

### 4. (İsteğe bağlı) PostgreSQL — Karar önbelleği

Multi-agent refund uygulaması (`multi_agent.py`), cache’e ek olarak PostgreSQL’de kararları saklayabilir (exact + semantic hit, maliyet düşürme). Kullanmak için:

1. PostgreSQL kurun (örn. `brew install postgresql@16` veya Docker: `docker run -d -p 5432:5432 -e POSTGRES_PASSWORD=postgres postgres:16`).
2. Veritabanı oluşturun: `createdb refund_db` (veya psql ile `CREATE DATABASE refund_db;`).
3. `.env` içine ekleyin (veya tek satır: `DATABASE_URL=postgresql://postgres:postgres@localhost:5432/refund_db`):

   ```
   POSTGRES_HOST=localhost
   POSTGRES_PORT=5432
   POSTGRES_USER=postgres
   POSTGRES_PASSWORD=postgres
   POSTGRES_DB=refund_db
   ```

4. Uygulama açılışında tablo otomatik oluşturulur. Verileri görmek için pgAdmin veya DBeaver kullanabilirsiniz.

Bu değişkenleri tanımlamazsanız uygulama sadece cache (JSON + Excel) ile çalışır; DB devre dışı kalır.

### 5. Belgeleri ekleyin

- **bilgiler** klasörüne PDF (`.pdf`), Word (`.docx`, `.doc`) veya metin (`.txt`, `.md`) dosyalarınızı koyun.
- İlk çalıştırmada bu dosyalar taranıp vektör indeksine dönüştürülür; indeks `storage` klasörüne kaydedilir.

## Çalıştırma

**Basit RAG:** `python rag_app.py`  
**Agent (Notepad + Bellek + Araçlar):** `python rag_agent.py`

```bash
python rag_app.py
```

Tarayıcıda açılan adres (genelde `http://127.0.0.1:7860`) üzerinden soru kutusuna yazıp “Gönder” ile cevap alabilirsiniz.

## Proje Yapısı

```
Project with Ergun/
├── bilgiler/          # PDF, Word, .txt dosyalarınız
├── storage/           # LlamaIndex vektör indeksi (otomatik oluşur)
├── notepad.txt        # Agent notepad (rag_agent.py ile oluşur)
├── long_memory.json   # Uzun süreli bellek (rag_agent.py ile oluşur)
├── .env               # OPENAI_API_KEY (siz oluşturursunuz)
├── .env.example       # Örnek env dosyası
├── rag_app.py         # Basit RAG uygulaması
├── rag_agent.py       # Agent: Notepad + Bellek + Araçlar (tool döngüsü)
├── memory_utils.py    # Notepad ve uzun bellek okuma/yazma
├── requirements.txt
└── README.md
```

## RAG Agent (Notepad, Bellek, Araçlar)

`rag_agent.py` ile çalışan sürümde:

- **Kısa bellek:** Son 6 sohbet turu otomatik olarak agent’a verilir.
- **Uzun bellek:** `remember` / `recall` araçları ile kalıcı bilgi kaydedilir ve okunur (örn. isim, tercih).
- **Notepad:** Agent `read_notepad_tool` / `write_notepad_tool` ile notepad’i okuyup yazabilir; arayüzden de yenile/kaydet yapılır.
- **Araçlar (tools):** `search_documents` (belgelerde arama), notepad ve bellek araçları. Agent hangi aracı ne zaman kullanacağına kendisi karar verir (tool döngüsü).
- **Tool döngüsü:** LangChain `create_tool_calling_agent` + `AgentExecutor`: agent araç çağrıları yapar, sonuçlar geri verilir, gerekirse tekrar araç kullanır veya son cevabı üretir.

## Teknolojiler

- **LlamaIndex:** Belgelerin taranması ve vektör indeksine dönüştürülmesi.
- **LangChain + OpenAI:** Soru + bulunan metin → cevap üretimi.
- **Gradio:** Web arayüzü (soru kutusu + cevap alanı).

## Notlar

- İndeks ilk çalıştırmada veya **bilgiler** klasörüne yeni dosya ekledikten sonra yeniden oluşturulur (mevcut `storage` silinirse veya hata alırsanız tekrar oluşur).
- Cevap maliyeti OpenAI kullanımına bağlıdır; `gpt-4o-mini` varsayılan modeldir, `rag_app.py` içinden değiştirilebilir.

### Embedding model değişince (cache + DB temizliği)

Refund akışı sırasıyla: **cache exact hit → cache semantic hit → db exact hit → db semantic hit → RAG**. Embedding modelini değiştirdiğinizde (örn. `text-embedding-3-small` → `text-embedding-3-large`) eski cache/DB kayıtları yeni modelle uyumsuz olur. Düzeni korumak için temizlik script'ini çalıştırın:

```bash
python scripts/clear_decision_data.py
```

Bu script `decision_cache.json` dosyasını boşaltır ve PostgreSQL `refund_decisions` tablosunu truncate eder. Sonrasında tüm yeni kayıtlar seçili embedding modeliyle tutarlı şekilde yazılır.
