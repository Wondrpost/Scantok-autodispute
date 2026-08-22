"""YOLOv8 inference over sampled video frames and still images.

Media is reduced to a single Safe/Damaged/Invalid status. Buyer unboxing
videos go through analyze_unboxing_video, which splits the clip at the first
opening event so the buyer's own scissors are never scored as transit damage.
"""

from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Sequence

import cv2
import numpy as np

logger = logging.getLogger(__name__)

STATUS_SAFE = "Safe"
STATUS_DAMAGED = "Damaged"
STATUS_INVALID = "Invalid"
STATUS_NOT_OBSERVED = "NotObserved"

VIDEO_SUFFIXES = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v"}
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}

_MODELS_DIR = Path(__file__).resolve().parent.parent / "models"

MODEL_PATH = os.getenv("YOLO_MODEL_PATH", str(_MODELS_DIR / "bestv3.pt"))
IMG_SIZE = int(os.getenv("YOLO_IMG_SIZE", "640"))
BATCH_SIZE = int(os.getenv("YOLO_BATCH_SIZE", "4"))
CONF_THRESHOLD = float(os.getenv("YOLO_CONF_THRESHOLD", "0.35"))

SAMPLE_FPS = float(os.getenv("SAMPLE_FPS", "1.0"))
MAX_SAMPLED_FRAMES = int(os.getenv("MAX_SAMPLED_FRAMES", "90"))
MAX_DECODE_WIDTH = int(os.getenv("MAX_DECODE_WIDTH", "1280"))
DAMAGE_MIN_HITS = int(os.getenv("DAMAGE_MIN_HITS", "2"))

OPEN_CONTACT_RATIO = float(os.getenv("OPEN_CONTACT_RATIO", "0.35"))
OPEN_MOTION_RATIO = float(os.getenv("OPEN_MOTION_RATIO", "0.18"))
OPEN_CONSECUTIVE = int(os.getenv("OPEN_CONSECUTIVE", "2"))
OPEN_BACKOFF_SEC = float(os.getenv("OPEN_BACKOFF_SEC", "1.5"))
MAX_PRE_OPEN_SEC = float(os.getenv("MAX_PRE_OPEN_SEC", "60"))
MIN_PRE_FRAMES = int(os.getenv("MIN_PRE_FRAMES", "3"))

ENABLE_FALLBACK_HEURISTIC = os.getenv("DAMAGE_FALLBACK_HEURISTIC", "true").lower() == "true"
EDGE_DENSITY_THRESHOLD = float(os.getenv("EDGE_DENSITY_THRESHOLD", "0.085"))


def _keywords(env_var: str, defaults: tuple[str, ...]) -> tuple[str, ...]:
    raw = os.getenv(env_var, ",".join(defaults))
    return tuple(kw.strip().lower() for kw in raw.split(",") if kw.strip())


DAMAGE_KEYWORDS = _keywords("DAMAGE_CLASSES", (
    "damage", "damaged", "dent", "torn", "tear", "rip", "crush", "crumpl",
    "broken", "break", "wet", "leak", "scratch", "hole",
    "rusak", "penyok", "sobek", "basah", "robek",
))
PACKAGE_KEYWORDS = _keywords("PACKAGE_CLASSES", (
    "package", "packages", "box", "boxes", "parcel", "paket", "kardus",
))
INTERVENTION_KEYWORDS = _keywords("INTERVENTION_CLASSES", (
    "hand", "person", "finger", "scissor", "knife", "cutter", "blade",
    "tangan", "gunting", "pisau", "silet",
))
OPENING_ARTIFACT_KEYWORDS = _keywords("OPENING_ARTIFACT_CLASSES", (
    "seal_cut", "cut_tape", "tape_cut", "tape_removed", "unsealed",
    "flap_open", "opened", "open_box", "segel", "terbuka",
))
PRODUCT_KEYWORDS = _keywords("PRODUCT_CLASSES", (
    "product", "item", "goods", "barang", "produk", "isi",
))


class MediaAnalysisError(RuntimeError):
    """Media could not be opened or contained no usable frames."""


@dataclass(slots=True)
class MediaAnalysis:
    """Verdict for one media file."""

    source: str
    media_type: str
    status: str
    frames_analyzed: int
    damage_hits: int
    max_confidence: float
    detected_labels: List[str] = field(default_factory=list)
    method: str = "yolo"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source,
            "media_type": self.media_type,
            "status": self.status,
            "frames_analyzed": self.frames_analyzed,
            "damage_hits": self.damage_hits,
            "max_confidence": round(self.max_confidence, 4),
            "detected_labels": self.detected_labels,
            "method": self.method,
        }


@dataclass(slots=True)
class Detection:
    """One YOLO box, flattened out of the ultralytics Results object."""

    label: str
    conf: float
    box: tuple[float, float, float, float]


@dataclass(slots=True)
class FrameRecord:
    """Per-frame flags. Holds no pixels, so the full timeline stays in memory."""

    ts: float
    has_package: bool
    has_product: bool
    transit_damage: bool
    opening_artifact: bool
    product_damage: bool
    max_conf: float
    labels: List[str] = field(default_factory=list)


@dataclass(slots=True)
class UnboxingAnalysis:
    """Two independent verdicts over one unboxing video."""

    source: str
    media_type: str
    packaging_status: str
    packaging_damage_hits: int
    product_status: str
    product_damage_hits: int
    tampering_suspected: bool
    open_event_second: float | None
    pre_open_frames: int
    post_open_frames: int
    frames_analyzed: int
    max_confidence: float
    detected_labels: List[str] = field(default_factory=list)
    method: str = "phase-aware"

    def to_chain_point(self) -> Dict[str, Any]:
        """MediaStatus-shaped dict for chain-of-custody comparison.

        Reports packaging_status, not product_status: the seller's packing
        video and courier's handover photo both show the sealed exterior, so
        only the exterior is comparable across all three checkpoints.
        """
        return {
            "source": self.source,
            "media_type": self.media_type,
            "status": self.packaging_status,
            "frames_analyzed": self.pre_open_frames,
            "damage_hits": self.packaging_damage_hits,
            "max_confidence": round(self.max_confidence, 4),
            "detected_labels": self.detected_labels,
            "method": self.method,
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source,
            "media_type": self.media_type,
            "packaging_status": self.packaging_status,
            "packaging_damage_hits": self.packaging_damage_hits,
            "product_status": self.product_status,
            "product_damage_hits": self.product_damage_hits,
            "tampering_suspected": self.tampering_suspected,
            "open_event_second": (
                round(self.open_event_second, 2) if self.open_event_second is not None else None
            ),
            "pre_open_frames": self.pre_open_frames,
            "post_open_frames": self.post_open_frames,
            "frames_analyzed": self.frames_analyzed,
            "max_confidence": round(self.max_confidence, 4),
            "detected_labels": self.detected_labels,
            "method": self.method,
        }


_model = None
_model_lock = threading.Lock()
_INFERENCE_LOCK = threading.Lock()
_model_has_damage_classes = False
_model_has_package_classes = False
_model_has_intervention_classes = False
_model_has_product_classes = False


def _resolve_device() -> str:
    """Pick a device whose compute capability the installed torch supports.

    A GPU newer than anything the wheel was built for (sm_120 on cu118) has no
    PTX path, so degrade to CPU instead of dying on "no kernel image".
    """
    forced = os.getenv("YOLO_DEVICE")
    if forced:
        return forced

    try:
        import torch

        if not torch.cuda.is_available():
            logger.info("No CUDA device visible - running on CPU")
            return "cpu"

        major, minor = torch.cuda.get_device_capability(0)
        capability = major * 10 + minor
        name = torch.cuda.get_device_name(0)

        supported = set()
        for arch in torch.cuda.get_arch_list():
            digits = "".join(ch for ch in arch if ch.isdigit())
            if digits:
                supported.add(int(digits))

        if supported and capability not in supported and capability > max(supported):
            logger.error(
                "%s (sm_%d) is newer than this torch build supports (%s) - falling back to CPU",
                name, capability, sorted(supported),
            )
            return "cpu"

        logger.info("Using GPU %s (sm_%d)", name, capability)
        return "cuda:0"
    except Exception:
        logger.warning("CUDA probe failed - running on CPU", exc_info=True)
        return "cpu"


def _resolve_batch_size(default: int) -> int:
    """Scale the inference batch to available VRAM."""
    override = os.getenv("YOLO_BATCH_SIZE")
    if override:
        return max(1, int(override))
    if not DEVICE.startswith("cuda"):
        return 2
    try:
        import torch

        total_gb = torch.cuda.get_device_properties(0).total_memory / (1024 ** 3)
    except Exception:
        return default
    if total_gb >= 10:
        return 8
    if total_gb >= 6:
        return 4
    return 2


DEVICE = _resolve_device()
USE_HALF = DEVICE.startswith("cuda") and os.getenv("YOLO_HALF", "true").lower() == "true"
BATCH_SIZE = _resolve_batch_size(BATCH_SIZE)


def _is_damage_label(label: str) -> bool:
    low = str(label).lower()
    return any(kw in low for kw in DAMAGE_KEYWORDS)


def _is_package_label(label: str) -> bool:
    low = str(label).lower()
    return any(kw in low for kw in PACKAGE_KEYWORDS)


def _is_intervention_label(label: str) -> bool:
    low = str(label).lower()
    return any(kw in low for kw in INTERVENTION_KEYWORDS)


def _is_opening_artifact_label(label: str) -> bool:
    low = str(label).lower()
    return any(kw in low for kw in OPENING_ARTIFACT_KEYWORDS)


def _is_product_label(label: str) -> bool:
    low = str(label).lower()
    return any(kw in low for kw in PRODUCT_KEYWORDS)


def _is_transit_damage_label(label: str) -> bool:
    """Damage attributable to shipping, i.e. damage minus opening artifacts.

    Defined by subtraction so a single-class model emitting a generic
    "Damaged" still counts, while a future "seal_cut" class is excluded.
    """
    return _is_damage_label(label) and not _is_opening_artifact_label(label)


def get_model():
    """Load the shared YOLO model once and cache it."""
    global _model, _model_has_damage_classes, _model_has_package_classes
    global _model_has_intervention_classes, _model_has_product_classes

    if _model is not None:
        return _model

    with _model_lock:
        if _model is None:
            from ultralytics import YOLO

            logger.info("Loading %s on %s (half=%s)", MODEL_PATH, DEVICE, USE_HALF)
            model = YOLO(MODEL_PATH)
            model.to(DEVICE)

            names = list(getattr(model, "names", {}).values())
            _model_has_damage_classes = any(_is_damage_label(n) for n in names)
            _model_has_package_classes = any(_is_package_label(n) for n in names)
            _model_has_intervention_classes = any(_is_intervention_label(n) for n in names)
            _model_has_product_classes = any(_is_product_label(n) for n in names)

            if not _model_has_damage_classes:
                logger.warning(
                    "No damage class in %s - edge-density fallback: %s",
                    MODEL_PATH, ENABLE_FALLBACK_HEURISTIC,
                )
            if not _model_has_package_classes:
                logger.warning("No package class in %s - Invalid detection disabled", MODEL_PATH)
            logger.info(
                "Phase segmentation: T_open via %s | product assessment %s",
                "hand/tool contact" if _model_has_intervention_classes else "motion fallback",
                "enabled" if _model_has_product_classes else "disabled",
            )
            _model = model
    return _model


def warmup() -> None:
    """Run one dummy pass so the first real request is not penalised."""
    model = get_model()
    blank = np.zeros((IMG_SIZE, IMG_SIZE, 3), dtype=np.uint8)
    with _INFERENCE_LOCK:
        model.predict(blank, imgsz=IMG_SIZE, device=DEVICE, half=USE_HALF, verbose=False)
    del blank


def release_gpu_cache() -> None:
    """Return cached VRAM to the driver between media items."""
    if not DEVICE.startswith("cuda"):
        return
    try:
        import torch

        torch.cuda.empty_cache()
    except Exception:
        pass


def _downscale(frame: np.ndarray) -> np.ndarray:
    height, width = frame.shape[:2]
    if width <= MAX_DECODE_WIDTH:
        return frame
    scale = MAX_DECODE_WIDTH / float(width)
    return cv2.resize(
        frame,
        (MAX_DECODE_WIDTH, max(1, int(round(height * scale)))),
        interpolation=cv2.INTER_AREA,
    )


def iter_video_frames(
    path: Path,
    sample_fps: float = SAMPLE_FPS,
    max_frames: int = MAX_SAMPLED_FRAMES,
) -> Iterator[np.ndarray]:
    """Yield roughly sample_fps frames per second of footage."""
    for _, frame in iter_video_frames_ts(path, sample_fps, max_frames):
        yield frame


def iter_video_frames_ts(
    path: Path,
    sample_fps: float = SAMPLE_FPS,
    max_frames: int = MAX_SAMPLED_FRAMES,
) -> Iterator[tuple[float, np.ndarray]]:
    """Yield (timestamp_seconds, frame) for sampled frames only.

    grab() advances the demuxer without decoding, so only frames on a sampling
    boundary are ever turned into arrays.
    """
    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        raise MediaAnalysisError(f"Unable to open video: {path.name}")

    try:
        src_fps = capture.get(cv2.CAP_PROP_FPS)
        if not src_fps or src_fps <= 0 or src_fps != src_fps:
            src_fps = 30.0
        step = max(1, int(round(src_fps / max(sample_fps, 1e-3))))

        index = taken = 0
        while taken < max_frames:
            if not capture.grab():
                break
            if index % step == 0:
                ok, frame = capture.retrieve()
                if not ok or frame is None:
                    break
                yield index / src_fps, _downscale(frame)
                taken += 1
            index += 1

        if taken == 0:
            raise MediaAnalysisError(f"No decodable frames in video: {path.name}")
    finally:
        capture.release()


def _batched(items: Iterable[Any], size: int) -> Iterator[List[Any]]:
    batch: List[Any] = []
    for item in items:
        batch.append(item)
        if len(batch) >= size:
            yield batch
            batch = []
    if batch:
        yield batch


def _edge_density(frame: np.ndarray, box: Sequence[float] | None = None) -> float:
    """Fraction of strong edge pixels, as a damage proxy for models without a
    damage class. Crumpled packaging yields far more edges than intact."""
    region = frame
    if box is not None:
        x1, y1, x2, y2 = (int(max(0, v)) for v in box)
        if x2 > x1 and y2 > y1:
            region = frame[y1:y2, x1:x2]
    if region.size == 0:
        return 0.0
    gray = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(gray, 80, 200)
    return float(np.count_nonzero(edges)) / float(edges.size)


def _predict(frames: List[np.ndarray]):
    """Forward pass, degrading to single-frame inference on CUDA OOM."""
    model = get_model()
    with _INFERENCE_LOCK:
        try:
            return model.predict(
                frames,
                imgsz=IMG_SIZE,
                conf=CONF_THRESHOLD,
                device=DEVICE,
                half=USE_HALF,
                verbose=False,
            )
        except Exception as exc:
            if "out of memory" not in str(exc).lower():
                raise
            logger.warning("CUDA OOM on batch of %d - retrying one at a time", len(frames))
            release_gpu_cache()
            results = []
            for frame in frames:
                results.extend(
                    model.predict(
                        frame,
                        imgsz=IMG_SIZE,
                        conf=CONF_THRESHOLD,
                        device=DEVICE,
                        half=USE_HALF,
                        verbose=False,
                    )
                )
            return results


def _extract_detections(result) -> List[Detection]:
    boxes = result.boxes
    if boxes is None or len(boxes) == 0:
        return []
    names = result.names
    return [
        Detection(str(names.get(cls_id, cls_id)), float(conf), tuple(xyxy))
        for cls_id, conf, xyxy in zip(
            boxes.cls.int().tolist(), boxes.conf.tolist(), boxes.xyxy.tolist()
        )
    ]


def _score_batch(frames: List[np.ndarray]) -> tuple[int, float, List[str], str]:
    """Return (damaged_frame_count, max_confidence, labels, method)."""
    results = _predict(frames)

    hits = 0
    max_conf = 0.0
    labels: List[str] = []
    method = "yolo"

    for frame, result in zip(frames, results):
        frame_damaged = False
        best_box = None
        best_conf = 0.0

        for det in _extract_detections(result):
            labels.append(det.label)
            if det.conf > best_conf:
                best_conf, best_box = det.conf, det.box
            if _is_damage_label(det.label) and det.conf >= CONF_THRESHOLD:
                frame_damaged = True
                max_conf = max(max_conf, det.conf)

        if not frame_damaged and not _model_has_damage_classes and ENABLE_FALLBACK_HEURISTIC:
            density = _edge_density(frame, best_box)
            method = "edge-density-fallback"
            if density >= EDGE_DENSITY_THRESHOLD:
                frame_damaged = True
                max_conf = max(max_conf, min(1.0, density / EDGE_DENSITY_THRESHOLD * 0.5))

        if frame_damaged:
            hits += 1

    del results
    frames.clear()
    return hits, max_conf, labels, method


def _finalize(
    source: str,
    media_type: str,
    frames_analyzed: int,
    hits: int,
    max_conf: float,
    labels: List[str],
    method: str,
    min_hits: int,
) -> MediaAnalysis:
    # Zero hits only means Safe if a package was actually seen; media that
    # never showed one is unverifiable, not clean.
    package_seen = any(_is_package_label(label) for label in labels)
    if _model_has_package_classes and not package_seen:
        status = STATUS_INVALID
    elif hits >= min_hits:
        status = STATUS_DAMAGED
    else:
        status = STATUS_SAFE

    analysis = MediaAnalysis(
        source=source,
        media_type=media_type,
        status=status,
        frames_analyzed=frames_analyzed,
        damage_hits=hits,
        max_confidence=max_conf,
        detected_labels=sorted(set(labels))[:15],
        method=method,
    )
    logger.info(
        "Analyzed %s (%s): %s [%d/%d flagged, method=%s]",
        source, media_type, status, hits, frames_analyzed, method,
    )
    return analysis


def analyze_video(path: str | Path) -> MediaAnalysis:
    """Sample the video and return an aggregated status."""
    path = Path(path)
    if not path.is_file():
        raise MediaAnalysisError(f"Video not found: {path}")

    total_hits = total_frames = 0
    max_conf = 0.0
    labels: List[str] = []
    method = "yolo"

    try:
        for batch in _batched(iter_video_frames(path), BATCH_SIZE):
            total_frames += len(batch)
            hits, conf, batch_labels, batch_method = _score_batch(batch)
            total_hits += hits
            max_conf = max(max_conf, conf)
            labels.extend(batch_labels)
            if batch_method != "yolo":
                method = batch_method
    finally:
        release_gpu_cache()

    return _finalize(
        path.name, "video", total_frames, total_hits, max_conf, labels, method, DAMAGE_MIN_HITS
    )


def analyze_photo(path: str | Path) -> MediaAnalysis:
    """Run single-frame inference on a still image."""
    path = Path(path)
    if not path.is_file():
        raise MediaAnalysisError(f"Photo not found: {path}")

    frame = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if frame is None:
        raise MediaAnalysisError(f"Unable to decode image: {path.name}")

    try:
        hits, conf, labels, method = _score_batch([_downscale(frame)])
    finally:
        del frame
        release_gpu_cache()

    return _finalize(path.name, "image", 1, hits, conf, labels, method, min_hits=1)


def analyze_media(path: str | Path) -> MediaAnalysis:
    """Dispatch to the video or image analyzer by file extension."""
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix in VIDEO_SUFFIXES:
        return analyze_video(path)
    if suffix in IMAGE_SUFFIXES:
        return analyze_photo(path)
    raise MediaAnalysisError(f"Unsupported media type '{suffix}' for {path.name}")


def _overlap_ratio(inner: Sequence[float], outer: Sequence[float]) -> float:
    """Fraction of inner's own area falling inside outer.

    IoU is unusable for hand-on-package: a hand is tiny next to a carton, so
    IoU stays near zero even on full overlap.
    """
    ix1, iy1 = max(inner[0], outer[0]), max(inner[1], outer[1])
    ix2, iy2 = min(inner[2], outer[2]), min(inner[3], outer[3])
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    area = max(1e-6, (inner[2] - inner[0]) * (inner[3] - inner[1]))
    return inter / area


def _intervention_contact(dets: List[Detection]) -> float:
    """Highest hand/tool-on-package overlap in one frame."""
    packages = [d for d in dets if _is_package_label(d.label)]
    tools = [d for d in dets if _is_intervention_label(d.label)]
    if not packages or not tools:
        return 0.0
    return max(_overlap_ratio(t.box, p.box) for t in tools for p in packages)


def _motion_ratio(prev_gray: np.ndarray | None, cur_gray: np.ndarray) -> float:
    """Changed-pixel fraction between consecutive samples.

    Fallback for models without a hand/tool class; also picks up camera shake,
    so it is only used when the contact signal is unavailable.
    """
    if prev_gray is None or prev_gray.shape != cur_gray.shape:
        return 0.0
    diff = cv2.absdiff(prev_gray, cur_gray)
    return float(np.count_nonzero(diff > 25)) / float(diff.size)


def _classify_frame(dets: List[Detection], ts: float) -> FrameRecord:
    record = FrameRecord(
        ts=ts,
        has_package=False,
        has_product=False,
        transit_damage=False,
        opening_artifact=False,
        product_damage=False,
        max_conf=0.0,
    )

    for det in dets:
        record.labels.append(det.label)
        if det.conf < CONF_THRESHOLD:
            continue
        if _is_package_label(det.label):
            record.has_package = True
        if _is_product_label(det.label):
            record.has_product = True
            if _is_damage_label(det.label):
                record.product_damage = True
        if _is_opening_artifact_label(det.label):
            record.opening_artifact = True
        elif _is_transit_damage_label(det.label):
            record.transit_damage = True
            record.max_conf = max(record.max_conf, det.conf)

    return record


def analyze_unboxing_video(path: str | Path) -> UnboxingAnalysis:
    """Phase-aware analysis of a buyer's unboxing video.

    Streams the clip once to locate T_open, then judges pre-open frames on
    packaging integrity and post-open frames on product condition.
    """
    path = Path(path)
    if not path.is_file():
        raise MediaAnalysisError(f"Video not found: {path}")

    get_model()
    use_motion_fallback = not _model_has_intervention_classes
    method = "phase-aware-motion-fallback" if use_motion_fallback else "phase-aware"

    records: List[FrameRecord] = []
    open_ts: float | None = None
    consecutive = 0
    prev_gray: np.ndarray | None = None

    try:
        for batch in _batched(iter_video_frames_ts(path), BATCH_SIZE):
            stamps = [ts for ts, _ in batch]
            frames = [frame for _, frame in batch]
            results = _predict(frames)

            for ts, frame, result in zip(stamps, frames, results):
                dets = _extract_detections(result)
                records.append(_classify_frame(dets, ts))

                if open_ts is None:
                    triggered = (
                        _intervention_contact(dets) >= OPEN_CONTACT_RATIO
                        or records[-1].opening_artifact
                    )
                    if use_motion_fallback:
                        small = cv2.resize(frame, (320, 180), interpolation=cv2.INTER_AREA)
                        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
                        triggered = triggered or _motion_ratio(prev_gray, gray) >= OPEN_MOTION_RATIO
                        prev_gray = gray

                    # Hysteresis: a hand merely passing through must not truncate the clip.
                    consecutive = consecutive + 1 if triggered else 0
                    if consecutive >= OPEN_CONSECUTIVE:
                        open_ts = ts

            del results
            frames.clear()
    finally:
        release_gpu_cache()

    # Rewind: at 1 fps the real opening may precede the sample that caught it.
    cutoff = (open_ts - OPEN_BACKOFF_SEC) if open_ts is not None else float("inf")
    cutoff = min(cutoff, MAX_PRE_OPEN_SEC)

    pre = [r for r in records if r.ts <= cutoff]
    post = [r for r in records if open_ts is not None and r.ts >= open_ts]

    pre_with_package = [r for r in pre if r.has_package]
    packaging_hits = sum(1 for r in pre_with_package if r.transit_damage)

    if _model_has_package_classes and len(pre_with_package) < MIN_PRE_FRAMES:
        packaging_status = STATUS_INVALID
    elif packaging_hits >= DAMAGE_MIN_HITS:
        packaging_status = STATUS_DAMAGED
    else:
        packaging_status = STATUS_SAFE

    # An opened box before the buyer touched it means it arrived opened.
    tampering = (
        len(pre_with_package) >= MIN_PRE_FRAMES
        and any(r.opening_artifact for r in pre_with_package)
    )

    post_with_product = [r for r in post if r.has_product]
    product_hits = sum(1 for r in post_with_product if r.product_damage)

    if not post_with_product:
        product_status = STATUS_NOT_OBSERVED
    elif product_hits >= DAMAGE_MIN_HITS:
        product_status = STATUS_DAMAGED
    else:
        product_status = STATUS_SAFE

    labels = [label for r in records for label in r.labels]
    analysis = UnboxingAnalysis(
        source=path.name,
        media_type="video",
        packaging_status=packaging_status,
        packaging_damage_hits=packaging_hits,
        product_status=product_status,
        product_damage_hits=product_hits,
        tampering_suspected=tampering,
        open_event_second=open_ts,
        pre_open_frames=len(pre_with_package),
        post_open_frames=len(post_with_product),
        frames_analyzed=len(records),
        max_confidence=max((r.max_conf for r in records), default=0.0),
        detected_labels=sorted(set(labels))[:15],
        method=method,
    )

    logger.info(
        "Unboxing %s: T_open=%s | packaging=%s (%d/%d) | product=%s (%d/%d)%s",
        path.name,
        f"{open_ts:.1f}s" if open_ts is not None else "none",
        packaging_status, packaging_hits, len(pre_with_package),
        product_status, product_hits, len(post_with_product),
        " | TAMPERING" if tampering else "",
    )
    return analysis
