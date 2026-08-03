import { useRef, useState } from "react";
import { createWorker } from "tesseract.js";
import { Camera, Loader2, Send, X } from "lucide-react";

interface PhotoAnalyzeInputProps {
  onAnalyze: (text: string) => void;
  pending?: boolean;
}

export default function PhotoAnalyzeInput({ onAnalyze, pending }: PhotoAnalyzeInputProps) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [extractedText, setExtractedText] = useState("");
  const [ocrRunning, setOcrRunning] = useState(false);
  const [ocrError, setOcrError] = useState<string | null>(null);

  const handleFileSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setOcrError(null);
    setExtractedText("");
    setPreviewUrl(URL.createObjectURL(file));
    setOcrRunning(true);

    try {
      // 한국어 + 영어(URL/영문 섞여 나오는 경우 대비) 동시 인식
      const worker = await createWorker(["kor", "eng"]);
      const { data } = await worker.recognize(file);
      await worker.terminate();

      const cleaned = data.text.trim();
      if (!cleaned) {
        setOcrError("문자를 인식하지 못했습니다. 더 선명한 사진으로 다시 시도해주세요.");
      }
      setExtractedText(cleaned);
    } catch (err) {
      setOcrError("텍스트 인식 중 오류가 발생했습니다. 다시 시도해주세요.");
    } finally {
      setOcrRunning(false);
    }
  };

  const handleReset = () => {
    setPreviewUrl(null);
    setExtractedText("");
    setOcrError(null);
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const handleSubmit = () => {
    if (!extractedText.trim() || pending) return;
    onAnalyze(extractedText);
    handleReset();
  };

  return (
    <div className="bg-white rounded-2xl p-4 mb-4 shadow-[0_8px_20px_rgba(91,91,246,0.10)]">
      <p className="text-sm font-medium mb-2 text-ink">문자 캡처 사진으로 분석하기</p>

      {!previewUrl && (
        <button
          onClick={() => fileInputRef.current?.click()}
          className="w-full border-2 border-dashed border-gray-200 rounded-xl py-6 flex flex-col items-center gap-2 text-muted hover:border-brand hover:text-brand transition"
        >
          <Camera size={22} />
          <span className="text-sm">사진 촬영 또는 앨범에서 선택</span>
        </button>
      )}

      <input
        ref={fileInputRef}
        type="file"
        accept="image/*"
        capture="environment"
        className="hidden"
        onChange={handleFileSelect}
      />

      {previewUrl && (
        <div className="space-y-3">
          <div className="relative">
            <img
              src={previewUrl}
              alt="캡처한 문자 미리보기"
              className="w-full max-h-56 object-contain rounded-xl bg-gray-50"
            />
            <button
              onClick={handleReset}
              className="absolute top-2 right-2 bg-black/50 text-white rounded-full p-1"
              aria-label="다시 선택"
            >
              <X size={14} />
            </button>
          </div>

          {ocrRunning && (
            <div className="flex items-center gap-2 text-sm text-muted py-2">
              <Loader2 size={16} className="animate-spin" />
              텍스트 인식 중...
            </div>
          )}

          {ocrError && (
            <div className="bg-danger-bg text-danger-text rounded-xl p-3 text-sm">{ocrError}</div>
          )}

          {!ocrRunning && extractedText && (
            <>
              <p className="text-xs text-muted">
                인식된 텍스트입니다. 틀린 부분이 있으면 직접 수정한 뒤 분석하세요.
              </p>
              <textarea
                value={extractedText}
                onChange={(e) => setExtractedText(e.target.value)}
                className="w-full bg-gray-50 rounded-xl p-3 text-sm resize-none h-24 focus:outline-none focus:ring-2 focus:ring-brand"
              />
              <button
                onClick={handleSubmit}
                disabled={pending || !extractedText.trim()}
                className="w-full bg-brand text-white rounded-2xl py-3 font-medium text-sm flex items-center justify-center gap-1.5 shadow-[0_3px_0_0_#3E3ECF] active:translate-y-[2px] active:shadow-[0_1px_0_0_#3E3ECF] transition disabled:opacity-70"
              >
                {pending ? <Loader2 size={16} className="animate-spin" /> : <Send size={16} />}
                {pending ? "분석 중..." : "이 텍스트로 분석하기"}
              </button>
            </>
          )}
        </div>
      )}
    </div>
  );
}
