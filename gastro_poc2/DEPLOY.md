# Deploying gastro_poc2 (Render + Supabase)

This branch (`deploy`) is the RAG-free, production-shaped build. The app runs as a
normal long-lived Django/gunicorn web service on **Render**, with the database on
**Supabase** (managed Postgres).

> **Why not Vercel?** Vercel is built for frontend/serverless functions. Django is
> a long-running WSGI app; on Vercel it needs a serverless adapter, has an
> ephemeral filesystem, and generally fights the platform. Render (or Railway/
> Fly.io) runs it as-is. Supabase is a perfect fit for the DB either way.

---

## 1. Database — Supabase

1. Create a project at [supabase.com](https://supabase.com). Pick a strong DB password.
2. In **Project Settings → Database → Connection string**, copy the **URI** for the
   **Session pooler** (port **5432**, host `*.pooler.supabase.com`). It's IPv4 and
   behaves like a normal connection — the right choice for a persistent server like
   Render (the direct `db.<ref>.supabase.co` host is IPv6-only and Render can't reach it):
   ```
   postgresql://postgres.<ref>:<password>@aws-0-<region>.pooler.supabase.com:5432/postgres
   ```
3. Keep this string; it becomes `DATABASE_URL` on Render. `settings.py` reads it via
   `dj-database-url` and it takes precedence over the local `POSTGRES_*` vars.

## 2. Push this branch to GitHub

```bash
git add -A
git commit -m "Deploy build: remove RAG, add prod config"
git push -u origin deploy
```

## 3. Web service — Render

> **Monorepo note:** this repo holds both `gastro_poc/` (old Streamlit POC) and
> `gastro_poc2/` (this app). The Django app lives in the **`gastro_poc2`
> subfolder**, so Render must target it. `render.yaml` (at the repo root) already
> sets `rootDir: gastro_poc2`; for a manual service set **Root Directory** to
> `gastro_poc2`. `gastro_poc/` is never built or deployed.

**Option A — Blueprint (uses `render.yaml` at repo root, one click):**
1. Render Dashboard → **New → Blueprint** → connect the repo → pick the `deploy` branch.
2. Render reads `render.yaml` and creates the service. Fill in the `sync: false`
   secrets when prompted:
   - `DATABASE_URL` — the Supabase pooler URI from step 1
   - `OPENROUTER_API_KEY` — your OpenRouter key (`AI_PROVIDER=openrouter` is preset)
3. Deploy. `build.sh` installs deps, runs `collectstatic`, and applies migrations.

**Option B — Manual web service:**
- Environment: **Python**
- **Root Directory: `gastro_poc2`**  ← required (the app is in this subfolder)
- Build command: `./build.sh`
- Start command: `gunicorn config.wsgi:application`
- Env vars: `DJANGO_DEBUG=False`, `DJANGO_SECRET_KEY` (generate one),
  `DATABASE_URL`, `AI_PROVIDER=openrouter`, `AI_MODEL=nvidia/nemotron-3-nano-30b-a3b`,
  `OPENROUTER_API_KEY`.

`ALLOWED_HOSTS` / CSRF for the `*.onrender.com` URL are auto-detected in
`settings.py` via `RENDER_EXTERNAL_HOSTNAME` — nothing to set unless you add a
custom domain (then set `DJANGO_ALLOWED_HOSTS` and `DJANGO_CSRF_TRUSTED_ORIGINS`).

## 4. Doctor account

`build.sh` runs `python manage.py seed_doctor` on every deploy (it's idempotent),
so the `doctor` / `clinic123` account — which also has `/admin` access
(`is_staff`) — exists automatically. **No Shell needed** (Render's Shell tab is
paid-tier only).

To create a full superuser as well, either temporarily add
`python manage.py createsuperuser --noinput` with `DJANGO_SUPERUSER_*` env vars to
`build.sh`, or upgrade to a paid instance for Shell access. The `doctor` account
covers `/admin` for normal use.

## 5. Verify

- Visit `https://<your-app>.onrender.com/` → login page.
- Log in as `doctor` / `clinic123`, and register a patient to test the intake chat.
- `/admin` works with the superuser.

---

## Required environment variables

| Var | Value |
|-----|-------|
| `DJANGO_SECRET_KEY` | long random string (Render can generate) |
| `DJANGO_DEBUG` | `False` |
| `DATABASE_URL` | Supabase Session pooler URI (port 5432) |
| `AI_PROVIDER` | `openrouter` (or `gemini` \| `openai` \| `anthropic`) |
| `AI_MODEL` | `nvidia/nemotron-3-nano-30b-a3b` (any OpenRouter model id) |
| `OPENROUTER_API_KEY` | your OpenRouter key |
| `DJANGO_ALLOWED_HOSTS` | only if using a custom domain |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | only if using a custom domain, e.g. `https://emr.example.com` |

## Notes

- **Free tier** spins down when idle; first request after a nap is slow. Fine for a
  demo — upgrade for always-on.
- The `Procfile` is included so this also deploys unchanged on Railway/Heroku-style
  hosts (it adds a `release: migrate` phase those platforms honor).
- `docker-compose.yml` remains for **local** Postgres only; it is not used in prod.
