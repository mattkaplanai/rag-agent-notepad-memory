Run RAGAS evaluation on the Researcher agent's RAG pipeline using 5 DOT regulation questions.

---

## Steps to execute

**Step 1 — Run RAGAS evaluation inside the container**

```bash
docker exec refund-gradio python - <<'EOF'
import os
from ragas.metrics._faithfulness import faithfulness
from ragas.metrics._answer_relevance import answer_relevancy
from ragas.metrics._context_precision import context_precision
from ragas.llms import LangchainLLMWrapper
from ragas.embeddings import LangchainEmbeddingsWrapper
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from datasets import Dataset
from ragas import evaluate

from app.rag.indexer import build_or_load_index
from app.rag.retriever import hybrid_search

llm = LangchainLLMWrapper(ChatOpenAI(model='gpt-4o-mini', temperature=0))
emb = LangchainEmbeddingsWrapper(OpenAIEmbeddings(model='text-embedding-3-small'))
faithfulness.llm = llm
answer_relevancy.llm = llm
answer_relevancy.embeddings = emb
context_precision.llm = llm

QUESTIONS = [
    {'question': 'What is the time threshold for a significant delay on a domestic flight?', 'ground_truth': '3 hours'},
    {'question': 'What is the time threshold for a significant delay on an international flight?', 'ground_truth': '6 hours'},
    {'question': 'How many days does an airline have to refund a credit card purchase?', 'ground_truth': '7 business days'},
    {'question': 'How many days does an airline have to refund a non-credit card purchase?', 'ground_truth': '20 calendar days'},
    {'question': 'Can a passenger get a refund if they cancel within 24 hours of booking?', 'ground_truth': 'Yes, if the booking was made at least 7 days before departure.'},
]

print('Building RAG index...')
index = build_or_load_index()

questions, answers, contexts, ground_truths = [], [], [], []
for item in QUESTIONS:
    q = item['question']
    result = hybrid_search(index, q, top_k=5)
    ctx = [chunk.content for chunk in result.chunks]
    answer = ' '.join(ctx[:2])[:1000]
    questions.append(q); answers.append(answer); contexts.append(ctx); ground_truths.append(item['ground_truth'])

dataset = Dataset.from_dict({'question': questions, 'answer': answers, 'contexts': contexts, 'ground_truth': ground_truths})

print('Running RAGAS evaluation...')
result = evaluate(dataset, metrics=[faithfulness, answer_relevancy, context_precision])

scores = result.scores
def avg(lst): return round(sum(lst)/len(lst), 3) if lst else None
f_scores  = [s.get('faithfulness') for s in scores if s.get('faithfulness') is not None]
ar_scores = [s.get('answer_relevancy') for s in scores if s.get('answer_relevancy') is not None]
cp_scores = [s.get('context_precision') for s in scores if s.get('context_precision') is not None]

print(f'FAITHFULNESS:      {avg(f_scores)}')
print(f'ANSWER_RELEVANCY:  {avg(ar_scores)}')
print(f'CONTEXT_PRECISION: {avg(cp_scores)}')
EOF
```

**Step 2 — Display results**

Show a table:

| Metric | Score | Meaning |
|--------|-------|---------|
| **Faithfulness** | X.XX | Is the answer grounded in retrieved docs? (1.0 = perfect) |
| **Answer Relevancy** | X.XX | Does the retrieved content address the question? |
| **Context Precision** | X.XX | Are retrieved chunks relevant? (no noise) |

Then add a verdict:
- All scores ≥ 0.8 → "RAG pipeline is performing well."
- `answer_relevancy` < 0.5 → "Answer Relevancy is low — the retrieved chunks contain the answer but are too verbose/noisy. Consider reducing chunk size or TOP_K."
- `context_precision` < 0.7 → "Context Precision is low — retriever is pulling irrelevant chunks. Consider tuning BM25 weight or reducing RETRIEVAL_TOP_K."
- `faithfulness` < 0.8 → "Faithfulness is low — the model may be hallucinating beyond the retrieved context."

**Step 3 — If container is not running:**

Say: "Container is not running. Start it with: `docker compose up -d`"
