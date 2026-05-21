# Bike Troubleshooting Web Frontend

Deployable Next.js frontend for the Bike Troubleshooting Assistant.

## Local development

```bash
npm install
cp .env.example .env.local
npm run dev
```

Set:

```bash
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```

Start the FastAPI backend from the repository root:

```bash
uvicorn backend.app.main:app --reload
```

## Vercel deployment

Create a Vercel project with `web/` as the root directory.

Environment variable:

```bash
NEXT_PUBLIC_API_BASE_URL=https://your-backend-host.example.com
```

The backend must allow the Vercel origin through `CORS_ALLOWED_ORIGINS`.
