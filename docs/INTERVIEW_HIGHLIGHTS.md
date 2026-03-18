# What to Highlight in the Interview — JD ↔ Your Project

**Use this right before the call.** Side-by-side mapping + phrases to say.

---

## 1. JD ↔ Your project (direct mapping)

| What the JD asks for | What you actually built (say this) |
|----------------------|-------------------------------------|
| **AI-driven service automation in the travel industry** | I built an **AI refund decision system for airlines**: automates eligibility and formal letters using DOT regulations—flight cancellation, delay, baggage, schedule change. That’s travel + consumer service. |
| **Configure and maintain deployments … conversational flows, LLM prompt management, system orchestration** | I **configure and maintain** a multi-agent pipeline: Classifier → Researcher (RAG) → Analyst → Writer → Judge. Each agent has its own **prompt**; the **Judge** can override the pipeline. All config via env and code; runs in **Docker**. |
| **UAT and regression QA … measure accuracy, latency, conversational quality** | I don’t have voice UAT yet, but I **measure decision correctness**: **two-level cache** (exact match + semantic similarity) to avoid bad repeats, **output guard** with **citation validation** so we don’t return ungrounded answers. I think in terms of accuracy and safe fallbacks. |
| **Monitor operational health; analytics and logging** | I added **logging** in the API, a **health endpoint** (service + decision count), and **persist every decision** in PostgreSQL. I’ve laid the foundation; I want to go deeper with tools like Datadog or Amplitude. |
| **Partner integration … telephony, CRM, travel inventory** | I built a **REST API** for partners to submit cases and get structured decisions (validation, clear request/response). I integrated **AviationStack** for flight data. I haven’t wired telephony or CRM yet, but I’m comfortable with APIs and would pick up Twilio/Salesforce with docs and partner support. |
| **Define and track performance metrics … accuracy, escalation, latency** | I **define “good”** as correct decision + citations; the **Judge** and **output guard** enforce that. I’d like to add formal metrics (accuracy rate, escalation rate, latency) and use them to improve prompts and flows. |
| **Prompt engineering and test new conversational behaviors** | I **design and tune prompts** per agent (Classifier, Researcher, Analyst, Writer, Judge) and **test** via the cache and guard logic. I’ve iterated on prompt design to get consistent, policy-compliant outputs. |
| **Understand how telephony, CRM, AI interconnect; workflow optimization** | I **documented** how the pipeline and guards connect (e.g. GUARDS_FLOW.md): API → input guard → Classifier → multi-agent → Judge → output guard → persist. I think in terms of **workflow stages** and where to block or override. |
| **Automation scripts and tools for implementation and monitoring** | I have **scripts** for clearing decision data, rebuilding the index, and **Excel export** of decisions from the cache for review. The **cache** itself automates “don’t re-run the same or very similar case.” |
| **Incident manager; triage, communication, resolution** | I built **input and output guards** so we **block bad requests** and **override unsafe decisions** instead of serving them. That’s the same mindset: limit blast radius, safe fallback, then fix root cause. |

---

## 2. Must-say highlights (short phrases)

Say these when relevant—they map straight to the JD.

1. **“I built an AI system for the travel industry—airline refund decisions—using DOT regulations, so it’s the same domain: travel and consumer service.”**

2. **“I designed a multi-agent pipeline with a Judge that can override the main flow if it violates policy, plus input and output guards so we don’t run on bad input or return ungrounded answers.”**

3. **“I care about accuracy and latency: we have a two-level cache—exact match and semantic similarity—and citation validation in the output guard so responses are grounded in the regulations.”**

4. **“I exposed everything through a REST API with validation and persistence in PostgreSQL, and integrated an external travel API (AviationStack). I’m comfortable owning the API contract and adding more integrations.”**

5. **“I documented the flow—where guards run, what they block—so both engineers and stakeholders can understand how we keep the system safe and explainable.”**

6. **“I haven’t configured telephony or CRM yet, but I’ve built API-driven workflows and production safeguards; I’m eager to learn Twilio, Amazon Connect, or Salesforce in a partner context.”**

---

## 3. One strong closing line

**“I’ve already built AI-driven travel consumer service—refund decisions with multi-agent LLM, RAG over regulations, and production guards—and I want to bring that same mix of engineering rigor and clear outcomes to your partner deployments and integrations.”**

---

## 4. If they ask “What’s the most relevant thing you’ve done?”

**“Building the airline refund system: it’s travel, it’s consumer service, and it’s applied AI—multi-agent orchestration, RAG over official documents, prompt design, and production safeguards like input/output guards and citation validation. That’s the same kind of work this role does, just applied to voice/chat and partner integrations.”**
