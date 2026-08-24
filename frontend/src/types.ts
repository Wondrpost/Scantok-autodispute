/** Mirrors the FastAPI response in backend/app/main.py. */

export type MediaStatus = "Safe" | "Damaged" | "Invalid";
export type ProductStatus = "Safe" | "Damaged" | "NotObserved";
export type LiableParty = "seller" | "courier" | "buyer" | "none" | "unknown";

export type Checkpoint = "seller" | "courier" | "buyer";

/** Verdicts are a closed set; the copy map is keyed on it so a new backend
 *  verdict fails typecheck instead of rendering blank. */
export type Verdict =
  | "Klaim Disetujui, Kesalahan Penjual"
  | "Klaim Disetujui, Kesalahan Kurir"
  | "Klaim Ditolak, Manipulasi Pembeli"
  | "Klaim Ditolak, Tidak Ditemukan Kerusakan"
  | "Klaim Memerlukan Tinjauan Manual, Bukti Tidak Valid"
  | "Klaim Memerlukan Tinjauan Manual, Kemasan Utuh Namun Produk Rusak"
  | "Klaim Diteruskan, Indikasi Paket Dibuka di Jalur Pengiriman";

/** approved / rejected are terminal; review is the third, neutral state and
 *  must never be styled as either of the other two. */
export type VerdictGroup = "approved" | "rejected" | "review";

export interface MediaResult {
  source: string;
  media_type: "video" | "image";
  status: MediaStatus;
  frames_analyzed: number;
  damage_hits: number;
  max_confidence: number;
  detected_labels: string[];
  method: string;
}

export interface ProductAssessment {
  product_status: ProductStatus;
  product_damage_hits: number;
  tampering_suspected: boolean;
  open_event_second: number | null;
  pre_open_frames: number;
  post_open_frames: number;
  frames_analyzed: number;
  method: string;
}

export interface DisputeResponse {
  success: boolean;
  complaint: string;
  verdict: Verdict;
  claim_approved: boolean;
  requires_manual_review: boolean;
  liable_party: LiableParty;
  reasoning: string;
  chain_of_custody: Record<Checkpoint, MediaResult>;
  product_assessment: ProductAssessment;
  processing_seconds: number;
  device: string;
}

export interface ApiError {
  status: number;
  title: string;
  detail: string;
}
