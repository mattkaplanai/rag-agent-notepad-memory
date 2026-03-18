# Guard flow — Input & Output guards

Bu dokümanda input ve output guard’ların **hangi aşamada** çalıştığı ve **akış** gösterilir.

---

## Pipeline akışı (API: POST /api/v1/analyze/)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  REQUEST BODY: case_type, flight_type, ticket_type, payment_method,         │
│                accepted_alternative, description                            │
└─────────────────────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  AŞAMA 0: API + Serializer                                                  │
│  RefundRequestSerializer.is_valid() → 400 if invalid                        │
└─────────────────────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  AŞAMA 1: INPUT GUARD  ◄── app.guards.input_guard.run_input_guard(data)      │
│  • Prompt injection / jailbreak                                              │
│  • PII tespit (opsiyonel maskeleme → sanitized_data)                         │
│  • Konu kapsamı (sadece iade / havayolu)                                     │
│  → passed=False ise: block_response dön, pipeline’ı çalıştırma               │
└─────────────────────────────────────────────────────────────────────────────┘
                                        │ passed=True (veya sanitized_data)
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  AŞAMA 2: Classifier                                                        │
│  run_classifier(...) → ClassifierOutput                                      │
└─────────────────────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  AŞAMA 3: Multi-Agent (Supervisor)                                           │
│  Researcher → Analyst → Writer → supervisor_decision                         │
└─────────────────────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  AŞAMA 4: Judge                                                              │
│  run_judge(classifier_output, supervisor_decision) → override uygulanır      │
│  → final_decision                                                            │
└─────────────────────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  AŞAMA 5: OUTPUT GUARD  ◄── app.guards.output_guard.run_output_guard(final)  │
│  • decision ∈ {APPROVED, DENIED, PARTIAL, ERROR}                             │
│  • Citation grounding (citation_validator ile uyum)                         │
│  • İçerik politika (reasons / letter)                                        │
│  → passed=False ise: override_decision veya ERROR ile güvenli yanıt          │
└─────────────────────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  AŞAMA 6: Persist + Response                                                 │
│  RefundDecision.objects.create(...) → Response(serializer.data, 201)        │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Hangi guard hangi aşamada?

| Guard        | Çalıştığı aşama | Girdi                    | Çıktı              | passed=False ise davranış                          |
|-------------|------------------|---------------------------|--------------------|----------------------------------------------------|
| **Input**   | Serializer’dan hemen sonra, Classifier’dan önce | `validated_data` (dict) | `InputGuardResult`  | Pipeline çalışmaz; `block_response` ile yanıt dön |
| **Output**  | Judge’dan sonra, DB/response’dan önce           | `final_decision` (dict)  | `OutputGuardResult` | `override_decision` veya ERROR ile güvenli yanıt  |

---

## Dosya yapısı

```
app/
  guards/
    __init__.py       # run_input_guard, run_output_guard, *Result export
    input_guard.py    # run_input_guard(), InputGuardResult
    output_guard.py   # run_output_guard(), OutputGuardResult
docs/
  GUARDS_FLOW.md      # Bu akış dokümanı
```

---

## View’da kullanım (entegrasyon sonrası)

```python
# analyze_case içinde — Input guard
from app.guards import run_input_guard, run_output_guard

data = serializer.validated_data
input_result = run_input_guard(data)
if not input_result.passed:
    return Response(input_result.block_response, status=status.HTTP_400_BAD_REQUEST)
data = input_result.sanitized_data or data

# ... classifier → multi_agent → judge → final ...

# Output guard
output_result = run_output_guard(final)
if not output_result.passed:
    final = output_result.override_decision or build_error_decision(output_result.block_reason)

# ... RefundDecision.objects.create(...); return Response(...)
```

Bu entegrasyon henüz yapılmadı; sadece yapı ve akış tanımlandı.
