# Scantok Auto-Dispute System

Resolves "my package arrived damaged" claims automatically by cross-matching
damage evidence from three handover points and applying a fixed liability
table.

| Checkpoint | Evidence | Question |
| --- | --- | --- |
| 1. Seller | Packing video | Was it already damaged before shipping? |
| 2. Courier | Handover photo | Was it intact when the courier took it? |
| 3. Buyer | Unboxing video | Did the damage only appear here? |

The first checkpoint showing damage carries liability. The buyer's video is
analysed *phase-aware*: it is split at the moment the buyer starts opening the
box, so cutting tape is never scored as transit damage.

## Stack

**Backend** FastAPI · Ultralytics YOLOv8 · OpenCV · Docker
**Frontend** React · Vite · TypeScript

## Requirements

- Docker Desktop (with the NVIDIA Container Toolkit for GPU; CPU also works)
- Node.js 18+ for the frontend
- No API keys, no cloud account, no dataset download — the fine-tuned weights
  (`backend/models/bestv3.pt`) and the seller/courier sample evidence are both
  committed, so a fresh clone runs as-is.

## Run it

Two terminals.

**1. Backend**

```bash
cp backend/.env.example backend/.env      # optional; defaults work as-is
docker compose up --build
```

First build downloads the CUDA PyTorch wheels and takes several minutes;
later starts take about 20 seconds. Wait for:

```
Device: cuda:0 | batch size: 4
Model warmed up
Uvicorn running on http://0.0.0.0:8000
```

On a machine without a GPU, delete the `deploy:` block in `docker-compose.yml`
first — the service then logs `No CUDA device visible - running on CPU` and
works unchanged, just slower.

Confirm it is up:

```bash
curl http://localhost:8000/api/health
```

Both `seller_video_present` and `courier_photo_present` must be `true`.

**2. Frontend**

```bash
cd frontend
npm install
npm run dev
```

Open **http://localhost:5173**, write a complaint, pick any video file, and
submit. Requests are proxied to the backend, so no CORS setup is needed.

The backend alone can also be driven from its Swagger UI at
http://localhost:8000/docs.

## Sample evidence

`dummy_data/` holds the seller packing video and courier handover photo that
checkpoints 1 and 2 are read from — it stands in for the object storage and
logistics API of the real system. Both files are committed so the service runs
out of the box. Only the buyer's unboxing video is uploaded at request time.

## API

`POST /api/analyze-dispute` — `multipart/form-data`

| Field | Type | Required |
| --- | --- | --- |
| `buyer_video` | file | yes |
| `complaint` | string | yes |
| `order_id` | string | no |

Returns the verdict, a per-checkpoint `chain_of_custody` breakdown, and a
separate `product_assessment`. See [frontend/README.md](frontend/README.md)
for the full response contract.

## Layout

```
backend/app/       FastAPI service and the vision agent
backend/models/    bestv3.pt — fine-tuned YOLOv8 damage weights
backend/tests/     truth-table unit tests
frontend/src/      React claim UI
docker/            Dockerfile and build notes
dummy_data/        seller and courier sample evidence
docs/              architecture notes
```

## Tests

```bash
cd backend && pytest        # 18 tests, no GPU or media needed
cd frontend && npm run build
```

## Current limitations

Stated plainly, because the verdict logic depends on them:

- `bestv3.pt` has two classes (`package`, `Damaged`). It cannot see the inner
  product, so `product_status` always returns `NotObserved` and
  `tampering_suspected` always returns `false`. Both code paths are complete
  and activate as soon as weights with those classes are supplied.
- `T_open` (the moment the buyer starts opening the box) falls back to
  frame-motion detection, since the model has no `hand`/`tool` class. The
  precise contact-based path is implemented and switches on automatically.
- `DAMAGE_MIN_RATIO` (0.30) is a reasoned starting point, not a value
  calibrated against labelled packages.
- The appeal button in the UI has no endpoint behind it yet.

## GPU notes

`requirements.txt` defaults to the CUDA 12.8 wheels, which cover RTX 50/40/30/20
series. On an unsupported GPU the service logs a warning and runs on CPU rather
than crashing. Swap to the cu118 block in `requirements.txt` for older drivers.
