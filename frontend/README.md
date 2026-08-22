# Frontend

Placeholder. Scaffold your client here (Next.js, Vite + React, whatever the
team picks) and update this file with its own setup steps.

The backend serves CORS `*` by default; set `CORS_ORIGINS` in `backend/.env`
before deploying anywhere real.

## API contract

Base URL in local dev: `http://localhost:8000`

### `POST /api/analyze-dispute`

`multipart/form-data`

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `buyer_video` | file | yes | mp4/mov/avi/mkv/webm/m4v, max 200 MB |
| `complaint` | string | yes | 1–2000 chars |
| `order_id` | string | no | free-form reference |

Response `200`:

```jsonc
{
  "success": true,
  "complaint": "Kardus penyok parah",
  "verdict": "Klaim Disetujui, Kesalahan Kurir",
  "claim_approved": true,
  "requires_manual_review": false,
  "liable_party": "courier",          // seller | courier | buyer | none | unknown
  "reasoning": "Paket aman saat dipacking penjual namun ...",

  // Exterior integrity at each handover point. The buyer entry is its
  // PRE-open verdict, so all three are directly comparable.
  "chain_of_custody": {
    "seller":  { "source": "seller_video.mp4",  "media_type": "video", "status": "Safe",    "frames_analyzed": 42, "damage_hits": 0, "max_confidence": 0.0,  "detected_labels": ["package"], "method": "yolo" },
    "courier": { "source": "courier_photo.jpg", "media_type": "image", "status": "Damaged", "frames_analyzed": 1,  "damage_hits": 1, "max_confidence": 0.81, "detected_labels": ["package","Damaged"], "method": "yolo" },
    "buyer":   { "source": "tmpab12.mp4",       "media_type": "video", "status": "Damaged", "frames_analyzed": 6,  "damage_hits": 4, "max_confidence": 0.77, "detected_labels": ["package","Damaged"], "method": "phase-aware" }
  },

  // Buyer-video-only axis. No other checkpoint ever saw inside the box.
  "product_assessment": {
    "product_status": "NotObserved",   // Safe | Damaged | NotObserved
    "product_damage_hits": 0,
    "tampering_suspected": false,      // parcel was already open on arrival
    "open_event_second": 7.0,          // null if opening was never detected
    "pre_open_frames": 6,
    "post_open_frames": 0,
    "frames_analyzed": 24,
    "method": "phase-aware-motion-fallback"
  },

  "processing_seconds": 12.4,
  "device": "cuda:0"
}
```

### Statuses worth handling explicitly

- `status: "Invalid"` on any checkpoint — the media never showed a package
  (blank wall, or the buyer tore in before filming the sealed box). Always
  paired with `requires_manual_review: true`.
- `product_status: "NotObserved"` — the product was never visible. Not the
  same as undamaged; don't render it as a pass.
- `tampering_suspected: true` — separate escalation path from damage.

Render `requires_manual_review: true` as a neutral "under review" state, not
as an approval or a rejection.

### `GET /api/health`

Returns device, model path, batch size, and whether the seller/courier
evidence files are present. Useful as a readiness check before enabling the
upload form.

### Errors

| Code | Meaning |
| --- | --- |
| 413 | Video over the size limit |
| 415 | Unsupported video format |
| 422 | Media could not be decoded |
| 424 | Seller/courier evidence missing on the server |
| 500 | Vision pipeline failure |

Interactive docs: http://localhost:8000/docs
