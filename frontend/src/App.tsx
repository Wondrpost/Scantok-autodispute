import { useCallback, useRef, useState } from "react";

import {
  ALLOWED_EXTENSIONS,
  MAX_UPLOAD_BYTES,
  fileExtension,
  formatBytes,
  submitDispute,
} from "./api";
import { DEMO_CASES } from "./demo";
import {
  AnalyzingView,
  ClaimForm,
  DemoPicker,
  ErrorView,
  ResultView,
  UploadingView,
} from "./screens";
import type { ApiError, DisputeResponse } from "./types";

type Phase = "form" | "uploading" | "analyzing" | "result" | "error";

// Stand-in for the order the buyer opened this screen from. In the real app
// this arrives from the host e-commerce navigation.
const ORDER = { name: "Headset Bluetooth ANC", id: "INV/20260823/001" };

export default function App() {
  const [phase, setPhase] = useState<Phase>("form");
  const [complaint, setComplaint] = useState("");
  const [video, setVideo] = useState<File | null>(null);
  const [formatError, setFormatError] = useState<string | null>(null);
  const [progress, setProgress] = useState(0);
  const [result, setResult] = useState<DisputeResponse | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const abortRef = useRef<(() => void) | null>(null);

  const chooseVideo = useCallback((file: File | null) => {
    setVideo(file);
    if (!file) {
      setFormatError(null);
      return;
    }
    if (!ALLOWED_EXTENSIONS.includes(fileExtension(file.name))) {
      setFormatError(
        `Format tidak didukung. Gunakan ${ALLOWED_EXTENSIONS.join(", ")}.`,
      );
      return;
    }
    if (file.size > MAX_UPLOAD_BYTES) {
      setFormatError(
        `Ukuran video ${formatBytes(file.size)} melebihi batas. Rekam lebih pendek atau turunkan kualitasnya.`,
      );
      return;
    }
    setFormatError(null);
  }, []);

  const send = useCallback(() => {
    if (!video || !complaint.trim()) return;

    setProgress(0);
    setError(null);
    setPhase("uploading");

    const { promise, abort } = submitDispute({
      video,
      complaint: complaint.trim(),
      orderId: ORDER.id,
      onUploadProgress: setProgress,
      onAnalysisStart: () => setPhase("analyzing"),
    });
    abortRef.current = abort;

    promise
      .then((response) => {
        setResult(response);
        setPhase("result");
      })
      .catch((err: ApiError) => {
        // An aborted upload returns to the form rather than an error screen.
        if (err.status === 0 && err.detail.includes("dibatalkan")) {
          setPhase("form");
          return;
        }
        setError(err);
        setPhase("error");
      })
      .finally(() => {
        abortRef.current = null;
      });
  }, [video, complaint]);

  const cancel = useCallback(() => abortRef.current?.(), []);

  const restart = useCallback(() => {
    setComplaint("");
    setVideo(null);
    setFormatError(null);
    setResult(null);
    setError(null);
    setProgress(0);
    setPhase("form");
  }, []);

  return (
    <div className="app">
      {phase === "form" && (
        <ClaimForm
          complaint={complaint}
          onComplaintChange={setComplaint}
          video={video}
          onVideoChange={chooseVideo}
          onSubmit={send}
          order={ORDER}
          formatError={formatError}
        />
      )}

      {phase === "uploading" && (
        <UploadingView progress={progress} onCancel={cancel} />
      )}

      {phase === "analyzing" && <AnalyzingView />}

      {phase === "result" && result && (
        <ResultView result={result} onRestart={restart} />
      )}

      {phase === "error" && error && (
        <ErrorView
          error={error}
          onRetry={send}
          onBack={() => setPhase("form")}
        />
      )}

      {import.meta.env.DEV && (
        <DemoPicker
          cases={DEMO_CASES}
          onPick={(response) => {
            setResult(response);
            setPhase("result");
          }}
          onReset={restart}
        />
      )}
    </div>
  );
}
