import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMessages } from "../hooks/useMessages";
import { analyzeMessage, bulkDeleteMessages, deleteAllMessages, ApiError } from "../api/smishing";
import { AlertTriangle, HelpCircle, BadgeCheck, ShieldX, ShieldCheck, Ban, Trash2, X } from "lucide-react";
import Badge from "../components/Badge";
import AnalyzeInput from "../components/AnalyzeInput";
import type { Verdict } from "../types";
import PhotoAnalyzeInput from "../components/PhotoAnalyzeInput";

const ICON_CHIP: Record<Verdict, { bg: string; text: string; icon: React.ReactNode }> = {
  danger: { bg: "bg-danger-bg", text: "text-danger-text", icon: <AlertTriangle size={18} /> },
  neutral: { bg: "bg-neutral-bg", text: "text-neutral-text", icon: <HelpCircle size={18} /> },
  safe: { bg: "bg-safe-bg", text: "text-safe-text", icon: <BadgeCheck size={18} /> },
  not_disaster: { bg: "bg-notice-bg", text: "text-notice-text", icon: <Ban size={18} /> },
};

export default function HomePage() {
  const { messages, loading, error, removeMessages, clearAllMessages } = useMessages();
  const navigate = useNavigate();
  const [analyzing, setAnalyzing] = useState(false);
  const [analyzeError, setAnalyzeError] = useState<string | null>(null);

  const [selectMode, setSelectMode] = useState(false);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const DAY_MS = 24 * 60 * 60 * 1000;
  const recent = messages.filter((m) => Date.now() - new Date(m.receivedAtISO).getTime() <= DAY_MS);
  const dangerCount = recent.filter((m) => m.verdict === "danger").length;
  const safeCount = recent.filter((m) => m.verdict === "safe").length;

  const handleAnalyze = async (text: string) => {
    setAnalyzeError(null);
    setAnalyzing(true);
    try {
      const created = await analyzeMessage({ raw_text: text, device_id: "web-client" });
      navigate(`/detail/${created.message_id}`);
    } catch (err) {
      setAnalyzeError(err instanceof ApiError ? err.message : "분석 요청에 실패했습니다. 잠시 후 다시 시도해주세요.");
    } finally {
      setAnalyzing(false);
    }
  };

  const toggleSelectMode = () => {
    setSelectMode((prev) => !prev);
    setSelectedIds(new Set());
    setDeleteError(null);
  };

  const toggleSelected = (id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const handleDeleteSelected = async () => {
    if (selectedIds.size === 0) return;
    if (!window.confirm(`선택한 ${selectedIds.size}건을 삭제할까요?`)) return;

    setDeleting(true);
    setDeleteError(null);
    try {
      const ids = Array.from(selectedIds);
      await bulkDeleteMessages(ids);
      removeMessages(ids);
      setSelectedIds(new Set());
      setSelectMode(false);
    } catch (err) {
      setDeleteError(err instanceof ApiError ? err.message : "삭제에 실패했습니다. 잠시 후 다시 시도해주세요.");
    } finally {
      setDeleting(false);
    }
  };

  const handleDeleteAll = async () => {
    if (messages.length === 0) return;
    if (!window.confirm(`탐지 이력 전체(${messages.length}건)를 삭제할까요? 되돌릴 수 없습니다.`)) return;

    setDeleting(true);
    setDeleteError(null);
    try {
      await deleteAllMessages();
      clearAllMessages();
      setSelectedIds(new Set());
      setSelectMode(false);
    } catch (err) {
      setDeleteError(err instanceof ApiError ? err.message : "삭제에 실패했습니다. 잠시 후 다시 시도해주세요.");
    } finally {
      setDeleting(false);
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
      <PhotoAnalyzeInput onAnalyze={handleAnalyze} pending={analyzing} />

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

      {messages.length > 0 && (
        <div className="flex items-center justify-between mb-2 px-1">
          <p className="text-sm font-medium text-muted">탐지 이력 {messages.length}건</p>
          {!selectMode ? (
            <button
              onClick={toggleSelectMode}
              className="text-sm font-medium text-brand flex items-center gap-1"
            >
              <Trash2 size={14} /> 삭제 관리
            </button>
          ) : (
            <button
              onClick={toggleSelectMode}
              className="text-sm font-medium text-muted flex items-center gap-1"
            >
              <X size={14} /> 취소
            </button>
          )}
        </div>
      )}

      {selectMode && (
        <div className="flex items-center justify-between gap-2 mb-3 bg-white rounded-2xl p-3 shadow-[0_6px_16px_rgba(15,17,21,0.06)]">
          <span className="text-sm text-muted">{selectedIds.size}건 선택됨</span>
          <div className="flex items-center gap-2">
            <button
              onClick={handleDeleteSelected}
              disabled={selectedIds.size === 0 || deleting}
              className="px-3 py-1.5 rounded-lg bg-danger-bg text-danger-text text-sm font-medium disabled:opacity-40"
            >
              선택 삭제
            </button>
            <button
              onClick={handleDeleteAll}
              disabled={deleting}
              className="px-3 py-1.5 rounded-lg bg-danger text-white text-sm font-medium disabled:opacity-40"
            >
              전체 삭제
            </button>
          </div>
        </div>
      )}

      {deleteError && (
        <div className="bg-danger-bg text-danger-text rounded-2xl p-3.5 mb-3 text-sm text-center">
          {deleteError}
        </div>
      )}

      <div className="space-y-2.5">
        {messages.map((m) => {
          const chip = ICON_CHIP[m.verdict];
          const checked = selectedIds.has(m.id);
          return (
            <div
              key={m.id}
              onClick={() => (selectMode ? toggleSelected(m.id) : navigate(`/detail/${m.id}`))}
              className="bg-white rounded-2xl p-3.5 shadow-[0_6px_16px_rgba(15,17,21,0.06)] flex items-center gap-3 cursor-pointer active:scale-[0.98] transition"
            >
              {selectMode && (
                <input
                  type="checkbox"
                  checked={checked}
                  onChange={() => toggleSelected(m.id)}
                  onClick={(e) => e.stopPropagation()}
                  className="w-5 h-5 shrink-0 accent-brand"
                />
              )}
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
