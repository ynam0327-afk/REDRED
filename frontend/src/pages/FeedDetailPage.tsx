import { useState, useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { ArrowLeft } from "lucide-react";
import { getEventDetail, ApiError } from "../api/smishing";
import type { EventApi } from "../types";
import { EVENT_META, EVENT_LABEL } from "../utils/eventMeta";

export default function FeedDetailPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [data, setData] = useState<EventApi | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;
    let cancelled = false;
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const raw = await getEventDetail(id!);
        if (!cancelled) setData(raw);
      } catch (err) {
        if (!cancelled) setError(err instanceof ApiError ? err.message : "정보를 불러오지 못했습니다.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => { cancelled = true; };
  }, [id]);

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center py-20 text-muted">
        <div className="w-8 h-8 border-4 border-gray-200 border-t-brand rounded-full animate-spin mb-3" />
        <p className="text-sm">불러오는 중...</p>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="bg-danger-bg text-danger-text rounded-2xl p-6 text-center">
        <p className="font-medium mb-1">에러가 발생했습니다</p>
        <p className="text-sm">{error ?? "해당 정보를 찾을 수 없습니다."}</p>
      </div>
    );
  }

  const typeCode = data.incident_type ?? "";
  const meta = EVENT_META[typeCode] ?? EVENT_META.DEFAULT;
  const region = [data.sido_nm, data.sigungu_nm, data.eupmyeondong_nm].filter(Boolean).join(" ") || "지역 정보 없음";
  const dateStr = new Date(data.occurred_at).toLocaleString("ko-KR", {
    year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit",
  });
  const bodyText = (data as EventApi & { full_text?: string | null }).full_text || data.summary_title || "상세 내용이 없습니다.";

  return (
    <div className="space-y-3">
      <button onClick={() => navigate(-1)} className="flex items-center gap-1 text-sm text-muted mb-1">
        <ArrowLeft size={16} /> 목록으로
      </button>

      <div className="bg-white rounded-2xl overflow-hidden shadow-[0_8px_20px_rgba(15,17,21,0.06)]">
        <div className={`h-1.5 ${meta.accent}`} />
        <div className="p-4 flex items-center gap-3">
          <div className={`w-11 h-11 rounded-xl ${meta.bg} ${meta.text} flex items-center justify-center shrink-0`}>
            {meta.icon}
          </div>
          <div>
            <p className="font-semibold text-ink text-lg">{EVENT_LABEL[typeCode] ?? "재난 정보"}</p>
            <p className="text-xs text-muted mt-0.5">{dateStr}</p>
          </div>
        </div>
      </div>

      <div className="bg-white rounded-2xl p-4 shadow-[0_6px_16px_rgba(15,17,21,0.06)]">
        <p className="text-xs text-muted mb-1">지역</p>
        <p className="text-sm text-ink font-medium">{region}</p>
      </div>

      <div className="bg-white rounded-2xl p-4 shadow-[0_6px_16px_rgba(15,17,21,0.06)]">
        <p className="text-xs text-muted mb-1">내용</p>
        <p className="text-sm text-ink leading-relaxed whitespace-pre-wrap">{bodyText}</p>
      </div>
    </div>
  );
}