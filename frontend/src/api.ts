import type { ApiError, DisputeResponse } from "./types";

export const MAX_UPLOAD_BYTES = 2000 * 1024 * 1024;

export const ALLOWED_EXTENSIONS = ["mp4", "mov", "avi", "mkv", "webm", "m4v"];

const ERROR_TITLES: Record<number, string> = {
  400: "Data klaim belum lengkap",
  413: "Video terlalu besar",
  415: "Format video tidak didukung",
  422: "Video tidak bisa dibaca",
  424: "Bukti pembanding belum tersedia",
  500: "Terjadi gangguan sistem",
};

const ERROR_DETAILS: Record<number, string> = {
  400: "Pastikan keluhan sudah diisi dan video sudah dipilih.",
  413: `Ukuran video melebihi batas ${MAX_UPLOAD_BYTES / 1024 / 1024 / 1000} GB. Rekam ulang dengan durasi lebih pendek atau kualitas lebih rendah.`,
  415: `Gunakan format ${ALLOWED_EXTENSIONS.join(", ")}.`,
  422: "Filenya mungkin rusak atau belum selesai tersalin. Coba pilih ulang videonya.",
  424: "Bukti dari penjual atau kurir belum tersedia di sistem. Coba lagi beberapa saat.",
  500: "Sistem sedang bermasalah saat memeriksa video. Coba beberapa saat lagi.",
};

export function apiError(status: number, detail?: string): ApiError {
  return {
    status,
    title: ERROR_TITLES[status] ?? "Klaim gagal dikirim",
    detail: detail || ERROR_DETAILS[status] || "Coba ulangi beberapa saat lagi.",
  };
}

export function fileExtension(name: string): string {
  const dot = name.lastIndexOf(".");
  return dot === -1 ? "" : name.slice(dot + 1).toLowerCase();
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
  return `${(bytes / 1024 / 1024 / 1024).toFixed(2)} GB`;
}

export interface SubmitArgs {
  video: File;
  complaint: string;
  orderId?: string;
  /** 0..1 while bytes are in flight. */
  onUploadProgress: (fraction: number) => void;
  /** Fires once the body is fully sent and the server starts analysing. */
  onAnalysisStart: () => void;
}

export interface SubmitHandle {
  promise: Promise<DisputeResponse>;
  abort: () => void;
}

/** Uploads via XHR rather than fetch: fetch cannot report upload progress,
 *  and a multi-hundred-megabyte video needs a real progress bar. */
export function submitDispute({
  video,
  complaint,
  orderId,
  onUploadProgress,
  onAnalysisStart,
}: SubmitArgs): SubmitHandle {
  const xhr = new XMLHttpRequest();

  const promise = new Promise<DisputeResponse>((resolve, reject) => {
    const form = new FormData();
    form.append("buyer_video", video);
    form.append("complaint", complaint);
    if (orderId) form.append("order_id", orderId);

    xhr.upload.addEventListener("progress", (event) => {
      if (event.lengthComputable) {
        onUploadProgress(event.loaded / event.total);
      }
    });

    // Upload finished; the ~5s inference wait starts here.
    xhr.upload.addEventListener("load", () => {
      onUploadProgress(1);
      onAnalysisStart();
    });

    xhr.addEventListener("load", () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          resolve(JSON.parse(xhr.responseText) as DisputeResponse);
        } catch {
          reject(apiError(500, "Balasan dari sistem tidak bisa dibaca."));
        }
        return;
      }
      let detail = "";
      try {
        const body = JSON.parse(xhr.responseText);
        detail = typeof body?.detail === "string" ? body.detail : "";
      } catch {
        /* non-JSON error body; fall back to the generic copy */
      }
      reject(apiError(xhr.status, detail));
    });

    xhr.addEventListener("error", () =>
      reject(
        apiError(
          0,
          "Koneksi ke server terputus. Periksa jaringan lalu coba lagi.",
        ),
      ),
    );

    xhr.addEventListener("abort", () =>
      reject(apiError(0, "Pengiriman klaim dibatalkan.")),
    );

    xhr.open("POST", "/api/analyze-dispute");
    xhr.send(form);
  });

  return { promise, abort: () => xhr.abort() };
}
