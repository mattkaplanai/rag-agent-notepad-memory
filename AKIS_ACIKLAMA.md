# "Uçuş iptal edilirse iade alır mıyım?" sorusunda arkada olan akış

Aşağıdaki adımlar, bu soruyu **RAG Agent** (`rag_agent.py`) ile sorduğunuzda arkada sırayla neler olduğunu anlatır.

---

## 1. Kullanıcı girişi

- Tarayıcıdaki metin kutusuna **"Uçuş iptal edilirse iade alır mıyım?"** yazılıp Gönder’e basılır.
- Gradio bu metni backend’e (Python) gönderir.

---

## 2. Kısa bellek (chat history) hazırlanır

- Son **6** sohbet turu (kullanıcı + asistan mesajları) LangChain mesaj formatına çevrilir.
- Bu mesaj listesi agent’a “bağlam” olarak verilir; böylece agent “az önce ne konuşmuştuk?” bilgisine sahip olur.
- İlk soruda bu liste boş olabilir.

---

## 3. AgentExecutor çağrılır

- **input:** `"Uçuş iptal edilirse iade alır mıyım?"`
- **chat_history:** Yukarıdaki mesaj listesi
- Agent, system prompt + chat_history + bu input ile çalışır.

---

## 4. İlk LLM çağrısı (Agent düşünüyor)

- OpenAI’a (gpt-4o-mini) şu anlama gelen bir istek gider:
  - “Belgeler, notepad ve belleği kullanıyorsun; belgelerle ilgili sorularda **search_documents** kullan.”
  - Kullanıcı sorusu: “Uçuş iptal edilirse iade alır mıyım?”
- Model bu soruyu belge sorusu olarak görür ve **bir araç (tool) çağrısı** döner: `search_documents(query="...")`.
- Yani cevabı hemen üretmez; önce belgelerde arama yapılmasını ister.

---

## 5. Tool döngüsü – Araç çalıştırılır

- **Çağrılan araç:** `search_documents`
- **Argüman:** Soruya uygun bir arama metni (örn. “uçuş iptal iade hakları” veya benzeri).
- **Arkada olan:**
  1. LlamaIndex’teki vektör indeksine bu arama metni gönderilir.
  2. Embedding (OpenAI `text-embedding-3-small`) ile sorgu vektörleştirilir.
  3. İndekste benzerlik (similarity) ile en uygun **8 parça** (chunk) seçilir.
  4. Bu parçalar tek metin gibi birleştirilir; bu metin **araç çıktısı** olarak agent’a geri verilir.
- Bu çıktı, DOT/refunds ile ilgili metinleri (ör. USDOT sayfaları, 14 CFR Part 259 vb.) içerir.

---

## 6. İkinci LLM çağrısı (Cevabı üretme)

- Agent’a tekrar mesaj gider; bu sefer:
  - Kullanıcı sorusu
  - + “search_documents şu sonucu döndü: [belge parçaları]”
- Model artık **cevabı üretir**: Türkçe, sadece bu belgelere dayalı (iptal, iade, 7 iş günü, 20 gün vb.).
- Bu cevap **tool çağrısı değil**, doğrudan metin olarak döner; AgentExecutor bunu “son çıktı” kabul eder ve döngüyü bitirir.

---

## 7. Cevabın kullanıcıya dönmesi

- AgentExecutor çıktı sözlüğünden **"output"** alınır (üretilen Türkçe cevap).
- Bu metin Gradio’daki sohbet kutusunda asistan mesajı olarak gösterilir.
- Aynı tur, **kısa belleğe** eklenir (bir sonraki soruda son 6 tur içinde yer alır).

---

## Özet (tek cümleyle)

**Kullanıcı soruyu yazar → Agent soruyu alır → “Belgelerle ilgili” deyip `search_documents` çağırır → LlamaIndex belgelerde arama yapar → Bulunan metin agent’a geri verilir → Agent bu metne göre Türkçe cevabı yazar → Cevap ekranda gösterilir.**

---

Terminalde bu adımları daha net görmek için `rag_agent.py` çalıştırıldığında **AKIŞ** logları açıldı; soruyu sorduğunuzda terminalde adım numaraları ve araç adları görünecek.
