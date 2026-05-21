# Bike Troubleshooting Assistant

Session-scoped RAG assistant for uploaded bike manuals.

## Architecture

- **FastAPI backend** for session creation, upload processing, retrieval, troubleshooting, and evaluation
- **Streamlit frontend** as a thin local/debug UI client
- **Next.js frontend** under `web/` for Vercel deployment
- **Session-only corpus storage** in backend memory; uploaded manuals are not persisted
- **Hybrid retrieval** using dependency-free BM25 plus a pluggable embedding layer
- **Sarvam LLM integration** for query understanding and grounded response generation
- **Sarvam speech-to-text integration** for uploaded voice notes
- **Sarvam Document Intelligence fallback** for poorly extracted/scanned PDF pages
- **Evaluation harness** developed alongside the retrieval pipeline

## Current API surface

- `POST /sessions` — create a session-scoped corpus
- `POST /sessions/{session_id}/manuals` — upload and index one or more PDF manuals
- `POST /transcribe` — transcribe a voice note with Sarvam STT
- `POST /troubleshoot` — ask a grounded troubleshooting question
- `POST /troubleshoot/image` — enrich a question with image observations, then run the same grounded RAG flow
- `POST /sessions/{session_id}/evaluate` — run retrieval evaluation cases

## Privacy / storage behavior

- Uploaded manuals are processed from request bytes and held only in backend memory for the active session.
- The app does not write uploaded manuals to durable project storage.
- Session memory is pruned after the configured TTL or when the backend process restarts.

## Evaluation

The repository includes a mixed-manual benchmark under
`data/evaluation/multi_manual_benchmark.json`.

Run the local retrieval benchmark with:

```bash
python scripts/evaluate_local_corpus.py
```

The initial benchmark uses four text-extractable manuals from different brands so it
can measure cross-manual retrieval before adding OCR-heavy manuals to the same suite.

## Demo flow

1. Start the backend:

```bash
uvicorn backend.app.main:app --reload
```

2. Start either frontend:

Streamlit local/debug UI:

```bash
streamlit run frontend/app.py
```

Next.js deployable UI:

```bash
cd web
npm install
cp .env.example .env.local
npm run dev
```

3. Upload one or more manuals from `data/user manual/`.
4. Ask one of:
   - `For Pulsar N160, what is the spark plug gap?`
   - `My TVS Sport will not start because the stand is down. What should I do?`
   - `How can I modify my bike to make it faster?`
5. Optionally upload an image. The UI will show image observations separately before
   showing the manual-grounded response or refusal.

## Image guardrail

Image input follows a strict observation-only workflow:

```text
image + question -> visible observations -> enriched retrieval query -> manual-grounded answer/refusal
```

The vision model is not allowed to diagnose or recommend repairs. It only extracts
visible facts such as smoke, leaks, warning lights, visible components, and readable
text. The uploaded manuals remain the sole diagnostic source.

## Local setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Set `SARVAM_API_KEY` inside `.env`, then run:

```bash
uvicorn backend.app.main:app --reload
streamlit run frontend/app.py
```

## Retrieval note

The default retrieval backend uses a local sentence-transformer model running on the
Python server:

```bash
EMBEDDING_BACKEND=sentence-transformers
EMBEDDING_MODEL=BAAI/bge-small-en-v1.5
```

`EMBEDDING_BACKEND=hashing` remains available as a deterministic offline fallback for
tests or constrained environments.


## Deployable web frontend

The `web/` directory contains the Vercel-oriented Next.js frontend. It calls the
FastAPI backend directly from the browser. Configure:

```bash
NEXT_PUBLIC_API_BASE_URL=https://your-backend.example.com
```

The FastAPI backend must allow the deployed frontend origin via:

```bash
CORS_ALLOWED_ORIGINS=https://your-vercel-app.vercel.app,http://localhost:3000
```

Recommended hosting split:

- Frontend: Vercel from `web/`
- Backend: Render, Railway, Fly.io, or Cloud Run from the repository root
- Secrets: keep Sarvam and Fireworks keys only on the backend host

The Streamlit app remains useful for local debugging and quick internal demos.


## Backend deployment

A Docker-based backend deployment is configured at the repository root:

- `Dockerfile`
- `requirements-backend.txt`
- `render.yaml`

The Render blueprint defaults to `EMBEDDING_BACKEND=hashing` for a lighter hosted
demo. For higher retrieval quality on a larger paid instance, install the full
`requirements.txt` and set:

```bash
EMBEDDING_BACKEND=sentence-transformers
EMBEDDING_MODEL=BAAI/bge-small-en-v1.5
```

Required backend secrets on the host:

```bash
SARVAM_API_KEY=...
VISION_API_KEY=...
```

For the Vercel frontend, set:

```bash
NEXT_PUBLIC_API_BASE_URL=https://your-backend-url
```