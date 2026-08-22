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

FastAPI · Ultralytics YOLOv8 · OpenCV · Docker

## Quick start

```bash
cp backend/.env.example backend/.env
docker compose up --build
```

Then open http://localhost:8000/docs.

Without Docker:

```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

`dummy_data/` must contain `seller_video.mp4` and `courier_photo.jpg` before
the endpoint will run — it stands in for the object storage and logistics API
of the real system. Check `GET /api/health` to confirm both are visible.

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
backend/     FastAPI service, YOLO weights, tests
frontend/    placeholder for the web client
docker/      Dockerfile and build context notes
dummy_data/  seller/courier evidence (contents gitignored)
docs/        architecture notes
```

## Tests

```bash
cd backend && pytest
```

The truth-table suite runs without a GPU, a model, or media files.

## GPU notes

`requirements.txt` defaults to the CUDA 12.8 wheels, which cover RTX 50/40/30/20
series. On an unsupported GPU the service logs a warning and runs on CPU rather
than crashing. Swap to the cu118 block in `requirements.txt` for older drivers.
