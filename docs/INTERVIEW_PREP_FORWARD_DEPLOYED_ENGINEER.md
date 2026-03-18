# Interview Prep: Forward Deployed Engineer (Travel / AI Service Automation)

Use this to connect **your experience** (Airlines Refund RAG + multi-agent system) to the job description and to prepare answers.

---

## 1. Role in One Sentence

You’re the person who **designs, deploys, and improves AI-driven service automation with travel partners**—from API and telephony/CRM integrations to LLM prompts, UAT, metrics, and incident response—while staying close to both engineering and customers.

---

## 2. Your Experience ↔ Job Requirements (Mapping)

| Job requirement | Your experience (use in answers) |
|-----------------|-----------------------------------|
| **Travel industry AI** | Airlines refund decision system: DOT regulations, refund rules, flight cancellation, baggage, schedule change—**directly travel + consumer service**. |
| **APIs, JSON, SQL, Python** | Django REST API (`POST /api/v1/analyze/`), AviationStack API, PostgreSQL, Python throughout (agents, RAG, guards, scripts). |
| **LLM systems, prompt design, conversational AI testing** | Multi-agent pipeline (Classifier → Researcher/Analyst/Writer → Judge), per-agent prompts, Judge override logic. Input/output guards for safety and quality. |
| **Configuring and maintaining deployments** | Docker Compose, env-based config, lazy-loaded pipeline, cache layer (exact + semantic). |
| **UAT / regression QA, accuracy, latency** | Decision cache (exact + semantic similarity), output guard + citation validation. You can say you’re used to “testing decision correctness and guarding bad outputs.” |
| **Monitoring, analytics, logging** | Logging in views, health endpoint, DB-backed decisions. You can say you’ve built the foundation and want to go deeper (Datadog, Amplitude, etc.). |
| **Partner integration & enablement** | REST API for “partners” to submit cases; serializers, validation, clear response contract. AviationStack as external travel-data integration. |
| **Data, quality, continuous improvement** | Metrics implied by decision outcomes (APPROVED/DENIED/PARTIAL), reasons, citations. You can speak to “defining what good looks like and guarding against bad answers.” |
| **System architecture & workflow automation** | Clear pipeline: Classifier → Supervisor (Researcher → Analyst → Writer) → Judge → Guards. Automation via scripts (e.g. clear_decision_data, index build). |
| **Incident / triage** | Input guard blocks bad requests; output guard overrides unsafe decisions. You can frame this as “production safeguards and graceful degradation.” |

---

## 3. Strong Talking Points (STAR-style)

### A. “Tell me about a project where you built AI for the travel industry.”

- **Situation:** Need to automate refund eligibility and formal letters for airline passengers (DOT rules).
- **Task:** Design a system that is accurate, auditable, and safe in production.
- **Action:** Built a multi-agent pipeline (Classifier → RAG Researcher → Analyst → Writer → Judge) with a **RAG layer** over DOT regulations (LlamaIndex, hybrid vector + BM25). Added **input guards** (prompt injection, PII, off-topic) and **output guards** (citation grounding, policy checks). Exposed via **Django REST API** and Gradio UI; **caching** for cost and latency.
- **Result:** Structured decisions (APPROVED/DENIED/PARTIAL) with reasons and citations; production-style safeguards; travel-domain and consumer-service relevance.

### B. “How do you ensure an LLM system is reliable and safe in production?”

- **Guards:** Input guard before the pipeline (block/mask); output guard after Judge (citation validation, override to safe response).
- **Structured output:** Pydantic schemas and a Judge step that can override the main pipeline if it violates policy.
- **Testing and cache:** Semantic cache to avoid re-running identical/similar cases; focus on measuring decision correctness and guarding bad outputs.
- **Next level:** You’re interested in more formal metrics (accuracy, escalation rate, latency) and tooling (e.g. Datadog, Amplitude) as in the role.

### C. “Describe a time you worked with APIs and external systems.”

- **REST API:** Designed and implemented Django REST endpoints for case submission and decision retrieval (validation, error handling, persistence).
- **External API:** Integrated AviationStack for flight data in a travel context.
- **Data layer:** PostgreSQL for decisions; structured request/response (JSON) and clear contracts for “partners” or internal consumers.

### D. “How do you work with non-technical stakeholders?”

- Frame your refund project: “I had to make the system’s behavior explainable—reasons, regulations, and a formal letter—so both operations and customers could trust it.”
- Emphasize documentation (e.g. GUARDS_FLOW.md), clear API contracts, and the ability to explain pipeline stages and where failures can be caught (guards, Judge).

---

## 4. Likely Interview Questions & Short Answers

- **Why Forward Deployed / customer-facing engineering?**  
  “I like being at the intersection of building robust systems and seeing them used in real workflows. The refund project showed me how important clarity and reliability are when the output affects customers and operations; I want to do that at scale with partners.”

- **Experience with telephony / voice / CRM?**  
  Be honest: “My hands-on experience is with REST APIs, LLM orchestration, and travel-domain logic. I haven’t yet worked with Twilio, Amazon Connect, or Salesforce directly, but I’ve integrated external APIs and am comfortable reading docs and working with partner engineers to implement and validate integrations.”

- **How do you measure and improve an AI assistant?**  
  “Define success (e.g. correct refund decision, citation grounding), add guards and validation, log inputs/outputs and failures, then use data to find gaps. I’ve done this with decision correctness and output guards; I want to add more formal metrics and A/B or prompt experiments.”

- **How do you handle an outage or a bad deployment?**  
  “Triage first: health checks, logs, and which layer failed (API, pipeline, external API). We have input/output guards to limit blast radius. I’d communicate status to stakeholders and roll back or fix forward depending on the issue.”

- **Tell me about a time you had to learn something new quickly.**  
  Use a concrete example: e.g. adding the guard flow, or integrating a new API/model into the pipeline while keeping the rest stable.

---

## 5. Gaps and How to Address Them

| Gap | How to phrase it |
|-----|------------------|
| No direct telephony (Twilio, Amazon Connect, etc.) | “I haven’t configured contact center platforms yet, but I’ve built API-driven workflows and am eager to learn CPaaS and voice flows.” |
| No CRM (Salesforce, Zendesk) integration | “I’ve worked with REST APIs and structured data; I’m confident I can pick up CRM webhooks and ticketing APIs with documentation and partner support.” |
| Limited “formal” UAT/QA for voice/chat | “I’ve focused on decision correctness, caching, and guard-based validation. I’m used to thinking about test cases and regression; I’d love to extend that to voice/chat UAT and metrics.” |
| No Jira/Confluence/Amplitude/Datadog yet | “I’ve used logging, health endpoints, and DB-backed outcomes. I’m comfortable adopting Jira, Confluence, and analytics tools in a team setting.” |

---

## 6. Questions to Ask Them

- How do you split time between embedded work with a single partner vs. supporting multiple partners?
- What does the typical lifecycle look like for a new partner (kickoff → first production flow → steady state)?
- How do you define and track “conversation accuracy” and “escalation rate” today?
- How do Forward Deployed Engineers work with Core AI Engineering when a change is needed in the model or prompt stack?
- Which telephony or CRM stack do most partners use (Twilio, Amazon Connect, Salesforce, etc.)?
- What’s the biggest operational or technical challenge the team has faced in the last 6 months?

---

## 7. One-Liner for “Why you?”

“I’ve built an AI-driven travel consumer service system—airline refund decisions—with multi-agent LLM orchestration, RAG over regulations, production guards, and a partner-ready API. I’m looking to apply that same mix of engineering rigor and clear outcomes to your deployments and partner integrations.”

Good luck with the interview.
