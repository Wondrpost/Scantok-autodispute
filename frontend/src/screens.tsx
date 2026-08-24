import { useEffect, useRef, useState } from "react";

import { ALLOWED_EXTENSIONS, fileExtension, formatBytes } from "./api";
import type { DemoCase } from "./demo";
import {
  IconBox,
  IconCamera,
  IconCheck,
  IconClock,
  IconCross,
  IconGallery,
  IconQuestion,
  IconSignal,
  IconWarning,
} from "./icons";
import type { ApiError, DisputeResponse } from "./types";
import {
  CHECKPOINT_LABEL,
  CHECKPOINT_ORDER,
  GROUP_LABEL,
  MEDIA_STATUS_LABEL,
  PRODUCT_STATUS_LABEL,
  PRODUCT_STATUS_NOTE,
  verdictCopy,
} from "./verdicts";

const MAX_COMPLAINT = 2000;
const LARGE_FILE_WARN = 300 * 1024 * 1024;

/* ------------------------------------------------------------------ form */

interface ClaimFormProps {
  complaint: string;
  onComplaintChange: (value: string) => void;
  video: File | null;
  onVideoChange: (file: File | null) => void;
  onSubmit: () => void;
  order: { name: string; id: string };
  formatError: string | null;
}

export function ClaimForm({
  complaint,
  onComplaintChange,
  video,
  onVideoChange,
  onSubmit,
  order,
  formatError,
}: ClaimFormProps) {
  const [guideOpen, setGuideOpen] = useState(false);
  const cameraRef = useRef<HTMLInputElement>(null);
  const galleryRef = useRef<HTMLInputElement>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [duration, setDuration] = useState<string | null>(null);

  useEffect(() => {
    setDuration(null);
    if (!video) {
      setPreview(null);
      return;
    }
    const url = URL.createObjectURL(video);
    setPreview(url);

    // Read duration off a detached element so the thumbnail stays untouched.
    const probe = document.createElement("video");
    probe.preload = "metadata";
    probe.src = url;
    probe.onloadedmetadata = () => {
      const total = Math.round(probe.duration);
      if (Number.isFinite(total)) {
        setDuration(`${Math.floor(total / 60)}:${String(total % 60).padStart(2, "0")}`);
      }
    };

    return () => URL.revokeObjectURL(url);
  }, [video]);

  const pick = (event: React.ChangeEvent<HTMLInputElement>) => {
    onVideoChange(event.target.files?.[0] ?? null);
    event.target.value = "";
  };

  const openCamera = () => {
    setGuideOpen(false);
    cameraRef.current?.click();
  };

  const ready = complaint.trim().length > 0 && video !== null && !formatError;

  return (
    <>
      <div className="scroll">
        <header>
          <h1 className="page-title">Ajukan Klaim Kerusakan</h1>
          <p className="page-sub">
            Ceritakan apa yang terjadi, lalu unggah video unboxing sebagai bukti.
          </p>
        </header>

        <div className="card order-card">
          <div className="order-thumb stripe" aria-hidden="true" />
          <div>
            <div className="order-name">{order.name}</div>
            <div className="order-id">Pesanan {order.id}</div>
          </div>
        </div>

        <div>
          <label className="label" htmlFor="complaint">
            Ceritakan kerusakannya <span className="req">*</span>
          </label>
          <div className="textarea-wrap">
            <textarea
              id="complaint"
              className="textarea"
              placeholder="Contoh: kotak penyok dan earcup kiri retak saat dibuka"
              maxLength={MAX_COMPLAINT}
              value={complaint}
              onChange={(event) => onComplaintChange(event.target.value)}
            />
            <span className="counter">
              {complaint.length}/{MAX_COMPLAINT}
            </span>
          </div>
        </div>

        <div>
          <span className="label">
            Video unboxing <span className="req">*</span>
          </span>

          {video ? (
            <div className="card video-picked">
              <div className="video-thumb stripe">
                {preview && <video src={preview} muted playsInline />}
              </div>
              <div className="video-meta">
                <div className="video-name">{video.name}</div>
                <div className="video-size">
                  {duration ? `${duration} · ` : ""}
                  {formatBytes(video.size)}
                </div>
              </div>
              <button className="link-accent" onClick={() => onVideoChange(null)}>
                Hapus
              </button>
            </div>
          ) : (
            <div className="dropzone">
              <p className="hint" style={{ marginBottom: 14 }}>
                Rekam paket <b>sebelum dibuka</b>, lalu lanjutkan membuka
              </p>
              <div className="btn-row">
                <button
                  className="btn-half btn-half-primary"
                  onClick={() => setGuideOpen(true)}
                >
                  <IconCamera /> Rekam Video
                </button>
                <button
                  className="btn-half"
                  onClick={() => galleryRef.current?.click()}
                >
                  <IconGallery /> Pilih dari Galeri
                </button>
              </div>
            </div>
          )}

          <input
            ref={cameraRef}
            type="file"
            accept="video/*"
            capture="environment"
            hidden
            onChange={pick}
          />
          <input
            ref={galleryRef}
            type="file"
            accept="video/*"
            hidden
            onChange={pick}
          />
        </div>

        {formatError && (
          <div className="notice notice-error">
            <IconWarning />
            <span>{formatError}</span>
          </div>
        )}

        {video && !formatError && video.size > LARGE_FILE_WARN && (
          <div className="notice">
            <IconSignal />
            <span>
              Videonya cukup besar ({formatBytes(video.size)}). Sebaiknya unggah
              lewat Wi-Fi agar tidak boros kuota.
            </span>
          </div>
        )}

        <button className="link-btn" onClick={() => setGuideOpen(true)}>
          Lihat panduan merekam
        </button>
      </div>

      <div className="dock">
        <button className="btn btn-primary" disabled={!ready} onClick={onSubmit}>
          Kirim Klaim
        </button>
      </div>

      {guideOpen && (
        <RecordingGuide
          onClose={() => setGuideOpen(false)}
          onStartCamera={openCamera}
        />
      )}
    </>
  );
}

/* ----------------------------------------------------------------- guide */

function RecordingGuide({
  onClose,
  onStartCamera,
}: {
  onClose: () => void;
  onStartCamera: () => void;
}) {
  return (
    <div
      className="sheet-backdrop"
      role="dialog"
      aria-modal="true"
      aria-label="Panduan merekam"
      onClick={onClose}
    >
      <div className="sheet" onClick={(event) => event.stopPropagation()}>
        <div className="sheet-grip" />
        <h2 className="sheet-title">Sebelum merekam</h2>
        <p className="hint">
          Rekam paket dalam kondisi UTUH minimal 5 detik, baru buka di depan
          kamera. Tanpa ini klaim tidak bisa diproses.
        </p>

        <ol className="steps">
          <li className="step">
            <span className="step-num">1</span>
            <span className="step-text">
              Nyalakan kamera saat paket <b>masih tertutup</b>
            </span>
          </li>
          <li className="step">
            <span className="step-num">2</span>
            <span className="step-text">
              Tunjukkan seluruh sisi paket, <b>min. 5 detik</b>
            </span>
          </li>
          <li className="step">
            <span className="step-num">3</span>
            <span className="step-text">
              Baru buka paket, <b>tanpa jeda rekaman</b>
            </span>
          </li>
        </ol>

        <button className="btn btn-primary" onClick={onStartCamera}>
          Mengerti, Buka Kamera
        </button>
      </div>
    </div>
  );
}

/* --------------------------------------------------------------- process */

export function UploadingView({
  progress,
  onCancel,
}: {
  progress: number;
  onCancel: () => void;
}) {
  const pct = Math.round(progress * 100);
  return (
    <>
      <div className="process">
        <div className="pct">{pct}%</div>
        <div className="bar">
          <div className="bar-fill" style={{ width: `${pct}%` }} />
        </div>
        <div>
          <p className="process-title">Mengunggah video</p>
          <p className="process-sub">
            Jangan tutup halaman ini sampai pengunggahan selesai.
          </p>
        </div>
      </div>
      <div className="dock">
        <button className="btn btn-ghost" onClick={onCancel}>
          Batalkan
        </button>
      </div>
    </>
  );
}

export function AnalyzingView() {
  return (
    <div className="process">
      <div className="spinner" role="status" aria-label="Sedang menganalisis" />
      <div>
        <p className="process-title">Memeriksa bukti</p>
        <p className="process-sub">
          Kami membandingkan videomu dengan bukti dari penjual dan kurir. Butuh
          beberapa detik.
        </p>
      </div>
      <div className="bar bar-indeterminate" />
    </div>
  );
}

/* ---------------------------------------------------------------- result */

export function ResultView({
  result,
  onRestart,
}: {
  result: DisputeResponse;
  onRestart: () => void;
}) {
  const copy = verdictCopy(result.verdict);
  const product = result.product_assessment;

  return (
    <>
      <div className="scroll">
        <div className="verdict-card" data-group={copy.group}>
          <div className="verdict-eyebrow">
            {copy.group === "approved" ? (
              <IconCheck />
            ) : copy.group === "rejected" ? (
              <IconCross />
            ) : (
              <IconClock />
            )}
            {GROUP_LABEL[copy.group]}
          </div>
          <h1 className="verdict-title">{result.verdict}</h1>
          <p className="verdict-reason">{copy.reasoning}</p>
        </div>

        <section>
          <div className="section-label">Perjalanan paket</div>
          <ol className="chain">
            {CHECKPOINT_ORDER.map((point) => {
              const item = result.chain_of_custody[point];
              const label = CHECKPOINT_LABEL[point];
              return (
                <li className="chain-item" key={point}>
                  <span className="chain-dot" data-status={item.status}>
                    {item.status === "Safe" ? (
                      <IconCheck />
                    ) : item.status === "Damaged" ? (
                      <IconWarning />
                    ) : (
                      <IconQuestion />
                    )}
                  </span>
                  <div>
                    <div className="chain-who">{label.who}</div>
                    <div className="chain-what">{label.what}</div>
                    <div className="chain-status" data-status={item.status}>
                      {MEDIA_STATUS_LABEL[item.status]}
                    </div>
                  </div>
                </li>
              );
            })}
          </ol>
        </section>

        <section>
          <div className="section-label">Kondisi produk</div>
          <div className="card">
            <div className="product-row">
              <div className="product-icon" data-status={product.product_status}>
                {product.product_status === "Damaged" ? (
                  <IconWarning />
                ) : product.product_status === "Safe" ? (
                  <IconBox />
                ) : (
                  <IconQuestion />
                )}
              </div>
              <div>
                <div className="product-status">
                  {PRODUCT_STATUS_LABEL[product.product_status]}
                </div>
                <div className="product-note">
                  {PRODUCT_STATUS_NOTE[product.product_status]}
                </div>
              </div>
            </div>

            {product.tampering_suspected && (
              <div className="tamper">
                Terdapat indikasi paket sempat dibuka sebelum sampai ke tanganmu.
                Kasus ini kami teruskan untuk pemeriksaan terpisah.
              </div>
            )}
          </div>
        </section>

        <p className="meta">
          Diperiksa dalam {result.processing_seconds.toFixed(1)} detik
        </p>
      </div>

      <div className="dock">
        {copy.showAppeal ? (
          <div style={{ display: "grid", gap: 10 }}>
            {/* Left visible but inert: the appeal route is part of the product
                design, while the endpoint behind it is out of MVP scope.
                Disabling states that plainly instead of faking a submission. */}
            <button className="btn btn-primary" disabled>
              Ajukan Banding
            </button>
            <p className="dock-note">Peninjauan manual belum tersedia di versi MVP ini</p>
            <button className="btn btn-ghost" onClick={onRestart}>
              Selesai
            </button>
          </div>
        ) : (
          <button className="btn btn-primary" onClick={onRestart}>
            Selesai
          </button>
        )}
      </div>
    </>
  );
}

/* ----------------------------------------------------------------- error */

export function ErrorView({
  error,
  onRetry,
  onBack,
}: {
  error: ApiError;
  onRetry: () => void;
  onBack: () => void;
}) {
  return (
    <>
      <div className="process">
        <div className="error-icon">
          <IconWarning />
        </div>
        <div>
          <p className="process-title">{error.title}</p>
          <p className="process-sub">{error.detail}</p>
        </div>
      </div>
      <div className="dock">
        <div style={{ display: "grid", gap: 10 }}>
          <button className="btn btn-primary" onClick={onRetry}>
            Coba Lagi
          </button>
          <button className="btn btn-ghost" onClick={onBack}>
            Kembali ke Formulir
          </button>
        </div>
      </div>
    </>
  );
}

/* ------------------------------------------------------------ demo picker */


/** Dev-only overlay for walking every verdict during a screen recording.
 *  Collapsed by default so it stays out of shot until needed. */
export function DemoPicker({
  cases,
  onPick,
  onReset,
}: {
  cases: DemoCase[];
  onPick: (response: DisputeResponse) => void;
  onReset: () => void;
}) {
  const [open, setOpen] = useState(false);

  if (!open) {
    return (
      <button
        className="demo-toggle"
        onClick={() => setOpen(true)}
        aria-label="Buka panel demo"
        title="Panel demo (hanya mode dev)"
      >
        &#9638;
      </button>
    );
  }

  return (
    <div className="demo-panel">
      <div className="demo-head">
        <span>Demo · semua putusan</span>
        <button onClick={() => setOpen(false)} aria-label="Tutup panel demo">
          <IconCross />
        </button>
      </div>
      <div className="demo-grid">
        {cases.map((item) => (
          <button
            key={item.label}
            className="demo-chip"
            onClick={() => onPick(item.response)}
          >
            {item.label}
          </button>
        ))}
        <button className="demo-chip demo-chip-reset" onClick={onReset}>
          Reset Formulir
        </button>
      </div>
    </div>
  );
}

export { ALLOWED_EXTENSIONS, fileExtension };
