# Docker

`backend.Dockerfile` builds from the **repository root**, not from `backend/`,
so it can reach both the source and the weights while a single root
`.dockerignore` controls what enters the context.

```bash
# via compose (recommended)
docker compose up --build

# or directly
docker build -f docker/backend.Dockerfile -t auto-dispute-backend:latest .
docker run -d --name dispute-api \
  -p 8000:8000 \
  --env-file backend/.env \
  -v "$(pwd)/dummy_data:/dummy_data:ro" \
  -e DUMMY_DATA_DIR=/dummy_data \
  --gpus all \
  auto-dispute-backend:latest
```

Drop `--gpus all` on a CPU-only host; the service detects the missing GPU and
falls back rather than failing.

## Layout inside the image

```
/srv/app/        application package
/srv/models/     bestv3.pt
/dummy_data/     mounted read-only at run time
```

Runs as uid 1000 (`appuser`). `HEALTHCHECK` polls `/api/health` every 30s with
a 45s grace period.

## Notes

- The base image is plain `python:3.11-slim`; CUDA comes from the torch wheels
  in `backend/requirements.txt`, not from the image.
- GPU passthrough needs the NVIDIA Container Toolkit on the host.
- The compose `env_file` block uses the `path` / `required` syntax, which needs
  Compose v2.24+. On older versions replace it with `env_file: [./backend/.env]`
  and create that file first.
