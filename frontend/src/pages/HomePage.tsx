import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMessages } from "../hooks/useMessages";
import { computeHeuristicScores } from "../utils/analyze";
import { postMessage, ApiError } from "../api/smishing";
import { AlertTriangle, HelpCircle, BadgeCheck, ShieldX, ShieldCheck } from "lucide-react";
import Badge from "../components/Badge";
import AnalyzeInput from "../components/AnalyzeInput";
import type { Verdict } from "../types";

const ICON_CHIP: Record<Verdict, { bg: string; text: string; icon: React.ReactNode }> = {
  danger: { bg: "bg-danger-bg", text: "text-danger-text", icon: <AlertTriangle size={18} /> },
  neutral: { bg: "bg-neutral-bg", text: "text-neutral-text", icon: <HelpCircle size={18} /> },
  safe: { bg: "bg-safe-bg", text: "text-safe-text", icon: <BadgeCheck size={18} /> },
};

export default function HomePage() {
  const { messages, loading, error } = useMessages();
  const navigate = useNavigate();
  const [analyzing, setAnalyzing] = useState(false);
  const [analyzeError, setAnalyzeError] = useState<string | null>(null);
  const DAY_MS = 24 * 60 * 60 * 1000;
  const recent = messages.filter((m) => Date.now() - new Date(m.receivedAtISO).getTime() <= DAY_MS);
  const dangerCount = recent.filter((m) => m.verdict === "danger").length;
  const safeCount = recent.filter((m) => m.verdict === "safe").length;

  const handleAnalyze = async (text: string) => {
    setAnalyzeError(null);
    setAnalyzing(true);
    try {
      const { urlRiskScore, textAuthenticityScore, detectedUrls } = computeHeuristicScores(text);
      const created = await postMessage({
        received_at: new Date().toISOString(),
        raw_text: text,
        detected_urls: detectedUrls.length ? detectedUrls : undefined,
        url_risk_score: urlRiskScore,
        text_authenticity_score: textAuthenticityScore,
        device_id: "web-client",
      });
      navigate(`/detail/${created.message_id}`);
    } catch (err) {
      setAnalyzeError(err instanceof ApiError ? err.message : "분석 요청에 실패했습니다. 잠시 후 다시 시도해주세요.");
    } finally {
      setAnalyzing(false);
    }
  };

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center py-20 text-muted">
        <div className="w-8 h-8 border-4 border-gray-200 border-t-brand rounded-full animate-spin mb-3" />
        <p className="text-sm">불러오는 중...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-danger-bg text-danger-text rounded-2xl p-6 text-center">
        <p className="font-medium mb-1">에러가 발생했습니다</p>
        <p className="text-sm">{error}</p>
      </div>
    );
  }

  return (
    <div>
      <AnalyzeInput onAnalyze={handleAnalyze} pending={analyzing} />

      {analyzeError && (
        <div className="bg-danger-bg text-danger-text rounded-2xl p-3.5 mb-4 text-sm text-center">
          {analyzeError}
        </div>
      )}

      <div className="grid grid-cols-2 gap-2.5 mb-4">
        <div className="bg-white rounded-2xl p-3.5 shadow-[0_8px_20px_rgba(91,91,246,0.10)]">
          <div className="w-8 h-8 rounded-lg bg-brand-bg flex items-center justify-center mb-2">
            <ShieldX size={16} className="text-brand" />
          </div>
          <p className="text-[11px] text-muted mb-0.5">24시간 차단</p>
          <p className="text-xl font-semibold text-ink">{dangerCount}건</p>
        </div>
        <div className="bg-white rounded-2xl p-3.5 shadow-[0_8px_20px_rgba(16,185,129,0.10)]">
          <div className="w-8 h-8 rounded-lg bg-safe-bg flex items-center justify-center mb-2">
            <ShieldCheck size={16} className="text-safe-text" />
          </div>
          <p className="text-[11px] text-muted mb-0.5">공식 확인</p>
          <p className="text-xl font-semibold text-ink">{safeCount}건</p>
        </div>
      </div>

      <div className="space-y-2.5">
        {messages.map((m) => {
          const chip = ICON_CHIP[m.verdict];
          return (
            <div
              key={m.id}
              onClick={() => navigate(`/detail/${m.id}`)}
              className="bg-white rounded-2xl p-3.5 shadow-[0_6px_16px_rgba(15,17,21,0.06)] flex items-center gap-3 cursor-pointer active:scale-[0.98] transition"
            >
              <div className={`w-10 h-10 rounded-xl ${chip.bg} ${chip.text} flex items-center justify-center shrink-0`}>
                {chip.icon}
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-0.5">
                  <span className="font-medium text-ink truncate">{m.sender}</span>
                  <Badge verdict={m.verdict} />
                </div>
                <p className="text-muted text-sm truncate">{m.content}</p>
              </div>
              <span className="text-xs text-gray-300 shrink-0">{m.receivedAt}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}