# dummy_data

Stands in for the object storage and logistics-partner API the real system
would query. `main.py` reads two files from here at request time:

| File | Role |
| --- | --- |
| `seller_video.mp4` | Seller's packing video (checkpoint 1) |
| `courier_photo.jpg` | Courier handover photo (checkpoint 2) |

Contents are gitignored — media is large and may contain real customer
footage. Drop your own samples in before running the service, or override the
filenames with `SELLER_VIDEO_NAME` / `COURIER_PHOTO_NAME`.

`GET /api/health` reports whether both files are visible to the service.
