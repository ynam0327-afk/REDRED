import { useState, useEffect, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { RefreshCw } from "lucide-react";
import { getEvents } from "../api/smishing";
import { adaptAlert } from "../utils/adaptAlert";
import { EVENT_META } from "../utils/eventMeta";
import type { DisasterAlertUi } from "../types";

const REGIONS = [
  "전체", "서울특별시", "부산광역시", "대구광역시", "인천광역시", "광주광역시",
  "대전광역시", "울산광역시", "세종특별자치시", "경기도", "강원특별자치도",
  "충청북도", "충청남도", "전북특별자치도", "전라남도", "경상북도", "경상남도", "제주특별자치도",
];

export default function FeedPage() {
  const [alerts, setAlerts] = useState<DisasterAlertUi[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [region, setRegion] = useState("전체");
  const [limit, setLimit] = useState(20);
  const navigate = useNavigate();

  const load = useCallback(async (isInitial: boolean) => {
    if (isInitial) setLoading(true);
    else setRefreshing(true);
    setError(null);
    try {
      const raw = await getEvents({ sido: region === "전체" ? undefined : region, limit });
      setAlerts(raw.map(adaptAlert));
      setLastUpdated(new Date());
    } catch {
      setError("재난 현황을 불러오지 못했습니다. 서버 연결을 확인해주세요.");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [region, limit]);

  useEffect(() => { load(true); }, [load]);
  useEffect(() => {
    const timer = setInterval(() => load(false), 60000);
    return () => clearInterval(timer);
  }, [load]);

  return (
    <div>
      <div className="flex gap-1.5 overflow-x-auto pb-2 mb-2">
        {REGIONS.map((r) => (
          <button
            key={r}
            onClick={() => { setRegion(r); setLimit(20); }}
            className={`shrink-0 px-3 py-1.5 rounded-full text-xs font-medium transition ${
              region === r ? "bg-brand text-white" : "bg-white text-muted border border-gray-200"
            }`}
          >
            {r}
          </button>
        ))}
      </div>

      <div className="flex items-center justify-between mb-3 px-1">
        <p className="text-xs text-muted">
          {lastUpdated && `마지막 업데이트 ${lastUpdated.toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit" })}`}
        </p>
        <button onClick={() => load(false)} disabled={refreshing} className="flex items-center gap-1 text-xs text-brand font-medium disabled:opacity-50">
          <RefreshCw size={13} className={refreshing ? "animate-spin" : ""} />
          새로고침
        </button>
      </div>

      {loading ? (
        <div className="flex flex-col items-center justify-center py-20 text-muted">
          <div className="w-8 h-8 border-4 border-gray-200 border-t-brand rounded-full animate-spin mb-3" />
          <p className="text-sm">불러오는 중...</p>
        </div>
      ) : error ? (
        <div className="bg-danger-bg text-danger-text rounded-2xl p-6 text-center">
          <p className="font-medium mb-1">에러가 발생했습니다</p>
          <p className="text-sm mb-3">{error}</p>
          <button onClick={() => load(true)} className="text-sm font-medium underline">다시 시도</button>
        </div>
      ) : alerts.length === 0 ? (
        <div className="text-center text-muted py-16"><p>표시할 재난 정보가 없습니다.</p></div>
      ) : (
        <>
          <div className="space-y-2.5">
            {alerts.map((alert) => {
              const meta = EVENT_META[alert.typeCode] ?? EVENT_META.DEFAULT;
              return (
                <div key={alert.id} onClick={() => navigate(`/feed/${alert.id}`)} className="bg-white rounded-2xl p-3.5 shadow-[0_6px_16px_rgba(15,17,21,0.06)] flex items-center gap-3 cursor-pointer active:scale-[0.98] transition">
                  <div className={`w-10 h-10 rounded-xl ${meta.bg} ${meta.text} flex items-center justify-center shrink-0`}>{meta.icon}</div>
                  <div className="flex-1 min-w-0">
                    <div className="flex justify-between items-center">
                      <span className="font-medium text-ink">{alert.disasterType}</span>
                      <span className="text-xs text-gray-300 shrink-0">{alert.date}</span>
                    </div>
                    <p className="text-sm text-muted mt-0.5 truncate">{alert.region}</p>
                  </div>
                </div>
              );
            })}
          </div>
          {alerts.length >= limit && (
            <button onClick={() => setLimit((l) => l + 20)} className="w-full mt-3 py-2.5 rounded-xl bg-white border border-gray-200 text-sm font-medium text-muted">
              더 보기
            </button>
          )}
        </>
      )}
    </div>
  );
}