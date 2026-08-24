/** Canned responses for demos and screen recordings.
 *
 *  Producing all seven verdicts from real media would need seven matched sets
 *  of seller/courier/buyer evidence. These fixtures use chains that the real
 *  truth table in backend/app/main.py would actually produce, so what is shown
 *  is reachable, not invented.
 *
 *  Dev-only: the picker is gated on import.meta.env.DEV and is dropped from
 *  production builds.
 */

import type {
  DisputeResponse,
  MediaResult,
  MediaStatus,
  ProductStatus,
  Verdict,
} from "./types";

function media(
  source: string,
  type: "video" | "image",
  status: MediaStatus,
  frames: number,
  hits: number,
): MediaResult {
  return {
    source,
    media_type: type,
    status,
    frames_analyzed: frames,
    damage_hits: hits,
    max_confidence: hits > 0 ? 0.78 : 0,
    detected_labels: hits > 0 ? ["Damaged", "package"] : ["package"],
    method: type === "image" ? "yolo" : "phase-aware-motion-fallback+dense-pre",
  };
}

function build(
  verdict: Verdict,
  chain: [MediaStatus, MediaStatus, MediaStatus],
  product: ProductStatus,
  opts: {
    approved: boolean;
    review: boolean;
    liable: DisputeResponse["liable_party"];
    tampering?: boolean;
  },
): DisputeResponse {
  const [seller, courier, buyer] = chain;
  return {
    success: true,
    complaint: "Kardus penyok parah dan isinya ikut rusak saat diterima.",
    verdict,
    claim_approved: opts.approved,
    requires_manual_review: opts.review,
    liable_party: opts.liable,
    reasoning: "(catatan teknis backend — UI memakai teksnya sendiri)",
    chain_of_custody: {
      seller: media("seller_video.mp4", "video", seller, 65, seller === "Damaged" ? 9 : 0),
      courier: media("courier_photo.jpg", "image", courier, 1, courier === "Damaged" ? 1 : 0),
      buyer: media("buyer_video.mp4", "video", buyer, 11, buyer === "Damaged" ? 5 : 0),
    },
    product_assessment: {
      product_status: product,
      product_damage_hits: product === "Damaged" ? 4 : 0,
      tampering_suspected: opts.tampering ?? false,
      open_event_second: 5.0,
      pre_open_frames: 11,
      post_open_frames: product === "NotObserved" ? 0 : 14,
      frames_analyzed: 97,
      method: "phase-aware-motion-fallback+dense-pre",
    },
    processing_seconds: 4.7,
    device: "cuda:0",
  };
}

export interface DemoCase {
  label: string;
  response: DisputeResponse;
}

export const DEMO_CASES: DemoCase[] = [
  {
    label: "Salah Penjual",
    response: build(
      "Klaim Disetujui, Kesalahan Penjual",
      ["Damaged", "Damaged", "Damaged"],
      "Damaged",
      { approved: true, review: false, liable: "seller" },
    ),
  },
  {
    label: "Salah Kurir",
    response: build(
      "Klaim Disetujui, Kesalahan Kurir",
      ["Safe", "Damaged", "Damaged"],
      "Damaged",
      { approved: true, review: false, liable: "courier" },
    ),
  },
  {
    label: "Manipulasi Pembeli",
    response: build(
      "Klaim Ditolak, Manipulasi Pembeli",
      ["Safe", "Safe", "Damaged"],
      "NotObserved",
      { approved: false, review: false, liable: "buyer" },
    ),
  },
  {
    label: "Tidak Ada Kerusakan",
    response: build(
      "Klaim Ditolak, Tidak Ditemukan Kerusakan",
      ["Safe", "Safe", "Safe"],
      "Safe",
      { approved: false, review: false, liable: "none" },
    ),
  },
  {
    label: "Bukti Tidak Valid",
    response: build(
      "Klaim Memerlukan Tinjauan Manual, Bukti Tidak Valid",
      ["Safe", "Invalid", "Safe"],
      "NotObserved",
      { approved: false, review: true, liable: "unknown" },
    ),
  },
  {
    label: "Produk Rusak Saja",
    response: build(
      "Klaim Memerlukan Tinjauan Manual, Kemasan Utuh Namun Produk Rusak",
      ["Safe", "Safe", "Safe"],
      "Damaged",
      { approved: false, review: true, liable: "unknown" },
    ),
  },
  {
    label: "Dibuka di Pengiriman",
    response: build(
      "Klaim Diteruskan, Indikasi Paket Dibuka di Jalur Pengiriman",
      ["Safe", "Safe", "Safe"],
      "NotObserved",
      { approved: false, review: true, liable: "unknown", tampering: true },
    ),
  },
];
