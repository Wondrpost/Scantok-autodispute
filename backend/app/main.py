"""FastAPI service for the E-commerce Auto-Dispute System.

Cross-matches damage evidence from three handover points (seller, courier,
buyer) and resolves liability from a fixed truth table. The buyer's unboxing
video is analysed phase-aware so its packaging and product verdicts stay
separate.
"""

from __future__ import annotations

import asyncio
import logging
import os
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field

from . import agent_vision
from .agent_vision import (
    STATUS_DAMAGED,
    STATUS_INVALID,
    STATUS_NOT_OBSERVED,
    MediaAnalysisError,
)

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger("auto_dispute")

BASE_DIR = Path(__file__).resolve().parent.parent
DUMMY_DATA_DIR = Path(os.getenv("DUMMY_DATA_DIR", BASE_DIR.parent / "dummy_data")).resolve()

SELLER_VIDEO_NAME = os.getenv("SELLER_VIDEO_NAME", "seller_video.mp4")
COURIER_PHOTO_NAME = os.getenv("COURIER_PHOTO_NAME", "courier_photo.jpg")

MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "200"))
MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024
UPLOAD_CHUNK_SIZE = 1024 * 1024

ALLOWED_VIDEO_SUFFIXES = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v"}

# One dispute at a time keeps peak VRAM and RSS predictable.
MAX_CONCURRENT_DISPUTES = int(os.getenv("MAX_CONCURRENT_DISPUTES", "1"))
_analysis_slot = asyncio.Semaphore(MAX_CONCURRENT_DISPUTES)

VERDICT_SELLER_FAULT = "Klaim Disetujui, Kesalahan Penjual"
VERDICT_COURIER_FAULT = "Klaim Disetujui, Kesalahan Kurir"
VERDICT_BUYER_FRAUD = "Klaim Ditolak, Manipulasi Pembeli"
VERDICT_NO_DAMAGE = "Klaim Ditolak, Tidak Ditemukan Kerusakan"
VERDICT_INVALID_EVIDENCE = "Klaim Memerlukan Tinjauan Manual, Bukti Tidak Valid"
VERDICT_TAMPERING = "Klaim Diteruskan, Indikasi Paket Dibuka di Jalur Pengiriman"
VERDICT_PRODUCT_ONLY = "Klaim Memerlukan Tinjauan Manual, Kemasan Utuh Namun Produk Rusak"

_ROLE_LABELS = {"seller": "penjual", "courier": "kurir", "buyer": "pembeli"}


def _join_id(items: list[str]) -> str:
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + " dan " + items[-1]


def resolve_verdict(
    seller: str,
    courier: str,
    buyer_packaging: str,
    buyer_product: str = STATUS_NOT_OBSERVED,
    tampering_suspected: bool = False,
) -> dict[str, object]:
    """Chain-of-custody truth table; first damaged checkpoint carries liability.

    buyer_packaging is the pre-open exterior verdict, the only buyer signal
    comparable with the other two checkpoints. buyer_product has no
    counterpart elsewhere and can therefore only escalate, never assign blame.
    """
    invalid_roles = [
        _ROLE_LABELS[role]
        for role, media_status in (
            ("seller", seller), ("courier", courier), ("buyer", buyer_packaging)
        )
        if media_status == STATUS_INVALID
    ]
    if invalid_roles:
        return {
            "verdict": VERDICT_INVALID_EVIDENCE,
            "claim_approved": False,
            "liable_party": "unknown",
            "requires_manual_review": True,
            "reasoning": (
                f"Bukti dari {_join_id(invalid_roles)} tidak menunjukkan paket sama sekali, "
                "sehingga rantai bukti tidak bisa diverifikasi. Klaim tidak bisa diputuskan "
                "otomatis dan perlu ditinjau oleh manusia."
            ),
        }

    # A parcel already open on arrival is theft, not damage - a different process.
    if tampering_suspected:
        return {
            "verdict": VERDICT_TAMPERING,
            "claim_approved": False,
            "liable_party": "unknown",
            "requires_manual_review": True,
            "reasoning": (
                "Segel/lakban paket sudah dalam kondisi terbuka pada video pembeli "
                "sebelum pembeli menyentuhnya. Ini indikasi paket dibuka di jalur "
                "pengiriman, bukan kasus kerusakan biasa - perlu investigasi terpisah."
            ),
        }

    if seller == STATUS_DAMAGED:
        return {
            "verdict": VERDICT_SELLER_FAULT,
            "claim_approved": True,
            "liable_party": "seller",
            "requires_manual_review": False,
            "reasoning": (
                "Kerusakan sudah terdeteksi pada video packing penjual, "
                "sebelum paket diserahkan ke kurir."
            ),
        }

    if courier == STATUS_DAMAGED:
        return {
            "verdict": VERDICT_COURIER_FAULT,
            "claim_approved": True,
            "liable_party": "courier",
            "requires_manual_review": False,
            "reasoning": (
                "Paket aman saat dipacking penjual namun sudah rusak pada foto "
                "bukti serah terima kurir."
            ),
        }

    if buyer_packaging == STATUS_DAMAGED:
        return {
            "verdict": VERDICT_BUYER_FRAUD,
            "claim_approved": False,
            "liable_party": "buyer",
            "requires_manual_review": False,
            "reasoning": (
                "Paket aman di titik penjual dan kurir, namun kemasan sudah rusak "
                "pada video pembeli sebelum paket dibuka. Kerusakan terjadi setelah "
                "paket diterima."
            ),
        }

    # Exterior clean everywhere but the product is broken: bad internal packing
    # and a factory defect fit the evidence equally, so escalate, don't accuse.
    if buyer_product == STATUS_DAMAGED:
        return {
            "verdict": VERDICT_PRODUCT_ONLY,
            "claim_approved": False,
            "liable_party": "unknown",
            "requires_manual_review": True,
            "reasoning": (
                "Kemasan luar utuh di ketiga titik pemeriksaan, tetapi produk di "
                "dalamnya terdeteksi rusak. Penyebabnya bisa packing dalam yang "
                "kurang baik, cacat produk, atau kerusakan setelah diterima - tidak "
                "bisa dipastikan otomatis karena tidak ada pihak lain yang melihat "
                "isi paket."
            ),
        }

    return {
        "verdict": VERDICT_NO_DAMAGE,
        "claim_approved": False,
        "liable_party": "none",
        "requires_manual_review": False,
        "reasoning": "Tidak ada kerusakan terdeteksi pada ketiga titik pemeriksaan.",
    }


class MediaStatus(BaseModel):
    source: str
    media_type: str = Field(..., description="'video' or 'image'")
    status: str = Field(..., description="'Safe', 'Damaged', or 'Invalid'")
    frames_analyzed: int
    damage_hits: int
    max_confidence: float
    detected_labels: list[str] = []
    method: str


class ProductAssessment(BaseModel):
    """Buyer-video-only axis: what is inside the box, and when it was opened."""

    product_status: str = Field(..., description="'Safe', 'Damaged', or 'NotObserved'")
    product_damage_hits: int
    tampering_suspected: bool
    open_event_second: float | None = Field(
        None, description="Second the buyer began opening; null if never detected"
    )
    pre_open_frames: int
    post_open_frames: int
    frames_analyzed: int
    method: str


class DisputeResponse(BaseModel):
    success: bool = True
    complaint: str
    verdict: str
    claim_approved: bool
    requires_manual_review: bool
    liable_party: str
    reasoning: str
    chain_of_custody: dict[str, MediaStatus] = Field(
        ..., description="Exterior-integrity comparison across the three handover points"
    )
    product_assessment: ProductAssessment
    processing_seconds: float
    device: str


class HealthResponse(BaseModel):
    # model_path collides with pydantic's reserved "model_" namespace.
    model_config = ConfigDict(protected_namespaces=())

    status: str
    device: str
    model_path: str
    batch_size: int
    dummy_data_dir: str
    seller_video_present: bool
    courier_photo_present: bool


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Dummy data directory: %s", DUMMY_DATA_DIR)
    logger.info("Device: %s | batch size: %d", agent_vision.DEVICE, agent_vision.BATCH_SIZE)
    try:
        await run_in_threadpool(agent_vision.warmup)
        logger.info("Model warmed up")
    except Exception:
        logger.exception("Warmup failed - retrying on first request")
    yield
    agent_vision.release_gpu_cache()


app = FastAPI(
    title="E-commerce Auto-Dispute System",
    description="Chain-of-custody 3-point cross-matching for package damage disputes.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _fetch_dummy_media(filename: str, kind: str) -> Path:
    """Resolve a stored evidence file, refusing paths outside DUMMY_DATA_DIR."""
    path = (DUMMY_DATA_DIR / filename).resolve()

    if DUMMY_DATA_DIR not in path.parents and path != DUMMY_DATA_DIR:
        raise HTTPException(status_code=400, detail=f"Invalid {kind} media path")

    if not path.is_file():
        raise HTTPException(
            status_code=status.HTTP_424_FAILED_DEPENDENCY,
            detail=f"{kind} evidence '{filename}' not found in {DUMMY_DATA_DIR}",
        )
    return path


async def _persist_upload(upload: UploadFile) -> Path:
    """Stream the upload to a temp file in fixed-size chunks."""
    suffix = Path(upload.filename or "buyer_video.mp4").suffix.lower()
    if suffix not in ALLOWED_VIDEO_SUFFIXES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=(
                f"Unsupported video format '{suffix}'. "
                f"Allowed: {sorted(ALLOWED_VIDEO_SUFFIXES)}"
            ),
        )

    handle = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    tmp_path = Path(handle.name)
    written = 0
    try:
        with handle:
            while chunk := await upload.read(UPLOAD_CHUNK_SIZE):
                written += len(chunk)
                if written > MAX_UPLOAD_BYTES:
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail=f"Buyer video exceeds the {MAX_UPLOAD_MB} MB limit",
                    )
                handle.write(chunk)
        if written == 0:
            raise HTTPException(status_code=400, detail="Buyer video is empty")
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise
    finally:
        await upload.close()

    logger.info("Buyer video stored at %s (%.2f MB)", tmp_path, written / 1024 / 1024)
    return tmp_path


def _run_chain_of_custody(seller_path: Path, courier_path: Path, buyer_path: Path):
    """Three sequential analyses - one decoder alive at a time.

    Only the buyer's media contains an unboxing, so only it needs phase
    segmentation; the seller's is a packing video and the courier's a still.
    """
    seller = agent_vision.analyze_media(seller_path)
    courier = agent_vision.analyze_media(courier_path)
    buyer = agent_vision.analyze_unboxing_video(buyer_path)
    return seller, courier, buyer


@app.get("/api/health", response_model=HealthResponse, tags=["system"])
async def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        device=agent_vision.DEVICE,
        model_path=agent_vision.MODEL_PATH,
        batch_size=agent_vision.BATCH_SIZE,
        dummy_data_dir=str(DUMMY_DATA_DIR),
        seller_video_present=(DUMMY_DATA_DIR / SELLER_VIDEO_NAME).is_file(),
        courier_photo_present=(DUMMY_DATA_DIR / COURIER_PHOTO_NAME).is_file(),
    )


@app.post(
    "/api/analyze-dispute",
    response_model=DisputeResponse,
    tags=["dispute"],
    summary="Run 3-point chain-of-custody analysis on a damage claim",
)
async def analyze_dispute(
    buyer_video: UploadFile = File(..., description="Unboxing video uploaded by the buyer"),
    complaint: str = Form(..., min_length=1, max_length=2000),
    order_id: str | None = Form(None),
) -> DisputeResponse:
    loop = asyncio.get_running_loop()
    started = loop.time()

    # Fail fast on missing stored evidence before accepting a large upload.
    seller_path = _fetch_dummy_media(SELLER_VIDEO_NAME, "Seller")
    courier_path = _fetch_dummy_media(COURIER_PHOTO_NAME, "Courier")

    buyer_path = await _persist_upload(buyer_video)

    try:
        async with _analysis_slot:
            try:
                seller, courier, buyer = await run_in_threadpool(
                    _run_chain_of_custody, seller_path, courier_path, buyer_path
                )
            except MediaAnalysisError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
            except Exception as exc:
                logger.exception("Vision pipeline failed")
                raise HTTPException(
                    status_code=500, detail=f"Vision pipeline failed: {exc}"
                ) from exc
    finally:
        buyer_path.unlink(missing_ok=True)

    decision = resolve_verdict(
        seller.status,
        courier.status,
        buyer.packaging_status,
        buyer.product_status,
        buyer.tampering_suspected,
    )

    logger.info(
        "Dispute %s | seller=%s courier=%s buyer_pkg=%s buyer_product=%s%s -> %s",
        order_id or "-", seller.status, courier.status,
        buyer.packaging_status, buyer.product_status,
        " TAMPERING" if buyer.tampering_suspected else "",
        decision["verdict"],
    )

    return DisputeResponse(
        complaint=complaint,
        verdict=str(decision["verdict"]),
        claim_approved=bool(decision["claim_approved"]),
        requires_manual_review=bool(decision["requires_manual_review"]),
        liable_party=str(decision["liable_party"]),
        reasoning=str(decision["reasoning"]),
        chain_of_custody={
            "seller": MediaStatus(**seller.to_dict()),
            "courier": MediaStatus(**courier.to_dict()),
            "buyer": MediaStatus(**buyer.to_chain_point()),
        },
        product_assessment=ProductAssessment(
            product_status=buyer.product_status,
            product_damage_hits=buyer.product_damage_hits,
            tampering_suspected=buyer.tampering_suspected,
            open_event_second=buyer.open_event_second,
            pre_open_frames=buyer.pre_open_frames,
            post_open_frames=buyer.post_open_frames,
            frames_analyzed=buyer.frames_analyzed,
            method=buyer.method,
        ),
        processing_seconds=round(loop.time() - started, 2),
        device=agent_vision.DEVICE,
    )
