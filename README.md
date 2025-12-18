Below is a **clean, professional, GitHub-ready README.md** you can drop straight into your repository.
It’s written the way **good open-source AI infra projects** present themselves: clear purpose, architecture, setup, and usage — without over-engineering or marketing fluff.

---

# 🧬 Clinical Trials AI Search & Summarization Platform

An AI-powered search application that retrieves clinical trials from **ClinicalTrials.gov**, summarizes results using **LLMs**, and delivers fast, paginated insights through a **ChatGPT-like UI**.

Built for **low latency**, **scalability**, and **clean separation of concerns** using chunked summarization, background jobs, and Redis caching.

---

## ✨ Features

- 🔍 Natural-language clinical trial search
- 🧠 LLM-powered summarization (chunk + aggregate)
- 📄 Paginated, scrollable results
- ⚡ Fast initial response with background processing
- 🗂 Structured & normalized trial data
- 🧾 Markdown-ready output (ChatGPT / Perplexity style)
- 🔁 Context-aware follow-up questions
- 🧰 MCP-compatible tool orchestration

---

## 🏗️ Architecture Overview

```text
User Query
   ↓
/ask (API)
   ↓
Query Normalizer (LLM)
   ↓
ClinicalTrials.gov API
   ↓
Chunking (5 studies per chunk)
   ↓
Chunk Summarizer (LLM, parallel)
   ↓
Redis Cache
   ↓
Frontend Pagination
   ↓
Aggregate Summarizer (background)
   ↓
Final Unified Summary
```

### Key Design Principles

- **Map–Reduce summarization**
- **Async background processing**
- **Stateless API + Redis state**
- **Frontend-driven pagination**
- **Model-agnostic orchestration**

---

## 🧩 Core Components

### Backend

- **Flask** – API server
- **Redis** – caching & job state
- **ClinicalTrials.gov v2 API** – data source
- **OpenAI API** – LLM orchestration

### LLM Roles

| Role                 | Model Type   |
| -------------------- | ------------ |
| Query refiner        | Fast / small |
| Chunk summarizer     | Fast / mid   |
| Aggregate summarizer | High-quality |

---

## 📦 Project Structure

```text
.
├── app.py                  # Flask entrypoint
├── routes/
│   ├── ask.py              # Search + job creation
│   ├── job_status.py       # Progress polling
│   ├── chunk.py            # Chunk pagination
│   └── final_summary.py    # Aggregate summary
├── services/
│   ├── trials_client.py    # ClinicalTrials API wrapper
│   ├── normalizer.py       # Field normalization
│   ├── chunker.py          # Chunk logic
│   ├── summarizer.py       # LLM prompts
│   └── background.py       # Async workers
├── cache/
│   └── redis.py
├── prompts/
│   ├── chunk_prompt.txt
│   └── aggregate_prompt.txt
├── frontend/               # UI (optional)
└── README.md
```

---

## ⚙️ Setup & Installation

### 1️⃣ Prerequisites

- Python **3.10+**
- Redis **6+**
- OpenAI API Key

---

### 2️⃣ Install Dependencies

```bash
pip install -r requirements.txt
```

---

### 3️⃣ Environment Variables

Create a `.env` file:

```env
OPENAI_API_KEY=sk-xxxx
REDIS_URL=redis://localhost:6379/0
FLASK_ENV=development
```

---

### 4️⃣ Start Redis

```bash
redis-server
```

---

### 5️⃣ Run the App

```bash
python app.py
```

Server runs on:

```
http://127.0.0.1:5000
```

---

## 🔌 API Endpoints

### `/ask` — Submit Query

```http
POST /ask
```

```json
{
  "query": "breast cancer trials without chemotherapy"
}
```

Response:

```json
{
  "job_id": "query:729204d47061f731",
  "status": "processing",
  "pages": 4,
  "message": "Summarizing 20 studies in background..."
}
```

---

### `/job_status` — Poll Progress

```http
GET /job_status?job_id=xxx
```

```json
{
  "progress_pct": 50,
  "chunks_completed": 2,
  "total_chunks": 4,
  "status": "processing"
}
```

---

### `/job_chunk` — Paginated Results

```http
GET /job_chunk?job_id=xxx&page=1
```

Returns a **Markdown summary** for that chunk.

---

### `/final_summary` — Unified Summary

```http
GET /final_summary?job_id=xxx
```

Returns the **final aggregated Markdown summary**.

---

## 🖥️ Frontend UX Flow

1. User submits query
2. UI shows:

   - “Searching trials…”
   - “Summarizing page 1 of 4…”

3. Page 1 renders immediately
4. Additional pages load on scroll
5. Final summary appears when ready

---

## 🚀 Performance Optimizations

- ✔ Chunked summarization
- ✔ Parallel LLM calls
- ✔ Redis caching
- ✔ Field normalization
- ✔ Minimal token prompts
- ✔ Lazy loading UI

Typical response:

- First page: **3–6s**
- Full summary: **8–15s**

---

## 🔐 Data Integrity Rules

- No hallucinated fields
- Missing fields omitted
- NCTId used as primary key
- Consistent PascalCase normalization

---

## 🧠 Prompt Strategy

- **Chunk Prompt** → pagination-safe summaries
- **Aggregate Prompt** → deduplicated, structured insights
- Prompts live in `/prompts` for easy iteration

---

## 📈 Scalability Notes

- Horizontal scaling via stateless Flask
- Redis handles shared state
- Background workers can move to Celery/RQ
- Model selection is fully configurable

---

## 🛠️ Future Improvements

- Streaming summaries
- User-specific context memory
- Saved searches
- Export (PDF / CSV)
- Relevance scoring
- Auth & rate limiting

---

## 📜 License

MIT License

---

## 🤝 Contributing

PRs welcome.
Please:

- Keep prompts deterministic
- Avoid breaking API contracts
- Maintain Markdown-only summaries

---

## 💡 Inspiration

- ChatGPT
- Perplexity AI
- LangChain Map–Reduce
- MCP Tooling Pattern

---

If you want next:

- CONTRIBUTING.md
- Frontend README
- Architecture diagram (SVG)
- Deployment guide (Docker / Railway / Fly.io)

Just say the word 👌
