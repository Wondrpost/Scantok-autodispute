/** User-facing copy, taken from the design canvas.
 *
 *  The backend's `reasoning` field stays as the audit record; what the buyer
 *  reads is written here in second person and deliberately softer. A claim
 *  outcome can accuse someone of fraud, so the wording is a design decision,
 *  not a byproduct of the API.
 */

import type {
  Checkpoint,
  MediaStatus,
  ProductStatus,
  Verdict,
  VerdictGroup,
} from "./types";

interface VerdictCopy {
  group: VerdictGroup;
  reasoning: string;
  /** Whether to surface the appeal route prominently. */
  showAppeal: boolean;
}

export const VERDICT_COPY: Record<Verdict, VerdictCopy> = {
  "Klaim Disetujui, Kesalahan Penjual": {
    group: "approved",
    reasoning:
      "Video penjual sudah menunjukkan paket dalam kondisi rusak sebelum diserahkan ke kurir. Tanggung jawab ada pada penjual.",
    showAppeal: false,
  },
  "Klaim Disetujui, Kesalahan Kurir": {
    group: "approved",
    reasoning:
      "Paket aman saat diserahkan penjual, namun sudah rusak saat diterima kurir. Tanggung jawab ada pada pihak kurir.",
    showAppeal: false,
  },
  "Klaim Ditolak, Manipulasi Pembeli": {
    group: "rejected",
    reasoning:
      "Paket tercatat aman hingga sampai ke tanganmu, namun video unboxing yang dikirim tidak menunjukkan kondisi asli paket secara meyakinkan.",
    showAppeal: true,
  },
  "Klaim Ditolak, Tidak Ditemukan Kerusakan": {
    group: "rejected",
    reasoning:
      "Ketiga video menunjukkan paket dan produk dalam kondisi baik di sepanjang perjalanan. Tidak ditemukan bukti kerusakan.",
    showAppeal: true,
  },
  "Klaim Memerlukan Tinjauan Manual, Bukti Tidak Valid": {
    group: "review",
    reasoning:
      "Salah satu video tidak menampilkan paket dengan jelas, sehingga sistem tidak bisa memastikan kondisinya. Tim kami akan meninjau langsung.",
    showAppeal: true,
  },
  "Klaim Memerlukan Tinjauan Manual, Kemasan Utuh Namun Produk Rusak": {
    group: "review",
    reasoning:
      "Kemasan terlihat utuh di semua titik, tetapi produk di dalamnya rusak. Kasus ini perlu diperiksa langsung oleh tim kami.",
    showAppeal: true,
  },
  "Klaim Diteruskan, Indikasi Paket Dibuka di Jalur Pengiriman": {
    group: "review",
    reasoning:
      "Video menunjukkan indikasi paket sempat dibuka selama pengiriman. Kasus ini kami teruskan untuk investigasi terpisah.",
    showAppeal: false,
  },
};

export const GROUP_LABEL: Record<VerdictGroup, string> = {
  approved: "Klaim Disetujui",
  rejected: "Klaim Ditolak",
  review: "Menunggu Tinjauan",
};

/** Fallback for a verdict string the frontend does not know yet. Renders as
 *  the neutral review state rather than guessing approve or reject. */
export const UNKNOWN_VERDICT: VerdictCopy = {
  group: "review",
  reasoning:
    "Hasil pemeriksaan sudah diterima namun belum dapat ditampilkan sepenuhnya. Tim kami akan meninjau klaim ini.",
  showAppeal: true,
};

export function verdictCopy(verdict: string): VerdictCopy {
  return VERDICT_COPY[verdict as Verdict] ?? UNKNOWN_VERDICT;
}

export const CHECKPOINT_LABEL: Record<Checkpoint, { who: string; what: string }> = {
  seller: { who: "Penjual", what: "Video saat paket dikemas" },
  courier: { who: "Kurir", what: "Foto saat paket diserahkan" },
  buyer: { who: "Kamu", what: "Video sebelum paket dibuka" },
};

export const CHECKPOINT_ORDER: Checkpoint[] = ["seller", "courier", "buyer"];

export const MEDIA_STATUS_LABEL: Record<MediaStatus, string> = {
  Safe: "Kondisi baik",
  Damaged: "Terlihat rusak",
  // Never "aman" - the package was simply not visible enough to judge.
  Invalid: "Tidak bisa dipastikan",
};

export const PRODUCT_STATUS_LABEL: Record<ProductStatus, string> = {
  Safe: "Produk terlihat baik",
  Damaged: "Produk terlihat rusak",
  // Explicitly not a pass: the product never appeared on camera.
  NotObserved: "Produk tidak terlihat di video",
};

export const PRODUCT_STATUS_NOTE: Record<ProductStatus, string> = {
  Safe: "Produk terlihat jelas dan tidak menunjukkan kerusakan.",
  Damaged: "Kerusakan pada produk terdeteksi setelah paket dibuka.",
  NotObserved:
    "Produk tidak pernah terlihat jelas di video, jadi kondisinya belum bisa dinilai.",
};
