This repository is a lightweight, open‑source, self‑hosted chatbot while running on a personal machine using free llms. It uses a Vue 3 + Vite frontend (TypeScript) and python with SQLite (including sqlite‑vec for vector storage) as the sole data store.

**Core goals**
- Run locally with no external DB or managed services.
- Persist sessions, messages, summaries, embeddings, and metadata in a single SQLite DB.
- Stream assistant responses via Server‑Sent Events (SSE).
- Enable easy switching between LLM providers using OpenAI‑compatible APIs (OpenRouter, Hugging Face, etc.).
- Support long‑context handling through automatic summarization, token budgeting, and semantic retrieval.
- Provide a simple, Docker‑friendly architecture for future tool‑calling and agent workflows.

**Current status**
- Monorepo with pnpm workspaces: `apps/pyapi` (python), `apps/web` (Vue 3), `packages/utils` (shared TS).
- Implemented basic API endpoints (health, providers, sessions, messages) and a Vue chat UI.
- SQLite schema defined for sessions, messages, summaries, embeddings, and tool calls.

**Planned milestones**
1. **Local Chat** – session CRUD, streaming SSE, OpenRouter & Hugging Face providers, token limits, basic UI.
2. **Memory & Retrieval** – embeddings with sqlite‑vec, retrieval of relevant history, conversation summaries, token budgeting.
3. **Tools & Agents** – tool‑call interface, backend execution, agent loop, optional tools (file search, web fetch, code execution, etc.).
4. **Media & Multimodal** – image/video model support, attachment handling, media metadata storage.

**Tech stack**
- **Backend:** Python, adapters for providers, SQLite + sqlite‑vec.
- **Frontend:** Vue 3, Vite, TypeScript, Pinia (or lightweight composables), native SSE.
- **Configuration:** `.env` file with provider keys, model selections, token limits, etc.

**Key architectural concepts**
- The backend acts as a context‑assembly engine: it builds each request from the system prompt, recent messages, optional summaries, and retrieved memories, then forwards it to the selected provider.
- Providers follow a unified interface (`streamChat`, `createEmbedding`, etc.) to simplify adding new models.
- Streaming is handled via SSE, with defined event types (message_start, delta, done, error, heartbeat).

**Next steps**
- Implement streaming responses over SSE.
- Add Hugging Face provider support and context assembly with summaries/retrieval.
- Introduce conversation summaries and token budgeting.
- Build Docker support and optional reverse‑proxy configuration.
