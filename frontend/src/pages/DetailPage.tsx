import { useState, useEffect } from "react";
import { useParams, useNavigate, useLocation } from "react-router-dom";
import { CheckCircle2, Trash2 } from "lucide-react";
import { getMessageDetail, deleteMessage, reportMessage, ApiError } from "../api/smishing";
import { adaptMessage } from "../utils/adapt";
import type { Message } from "../types";
import Alert from "../components/Alert";
import Button from "../components/Button";
import Modal from "../components/Modal";

export default function DetailPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  // 홈에서 방금 분석 직후 넘어온 경우, POST 응답을 바로 씀 (서버 캐싱 최대 10초라 재조회가 아직 안 될 수 있음)
  const initialMessage = (location.state as { initialMessage?: Message } | null)?.initialMessage ?? null;

  const [message, setMessage] = useState<Message | null>(initialMessage);
  const [loading, setLoading] = useState(!initialMessage);
  const [error, setError] = useState<string | null>(null);

  const [reported, setReported] = useState(false);
  const [reporting, setReporting] = useState(false);
  const [reportError, setReportError] = useState<string | null>(null);
  const [showReportModal, setShowReportModal] = useState(false);

  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;
    let cancelled = false;
    async function load() {
      if (!initialMessage) setLoading(true);
      setError(null);
      try {
        const raw = await getMessageDetail(id!);
        if (!cancelled) setMessage(adaptMessage(raw));
      } catch (err) {
        if (!cancelled) {
          // 방금 분석해서 넘어온 화면이면, 서버 캐싱(최대 10초)으로 재조회가 잠깐 실패할 수 있으니
          // 이미 보여줄 데이터(initialMessage)가 있으면 에러로 덮어쓰지 않음
          if (!initialMessage) {
            const msg = err instanceof ApiError ? err.message : "데이터를 불러오지 못했습니다.";
            setError(msg);
          }
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => { cancelled = true; };
  }, [id]);

  const handleReport = async () => {
    if (!id || reported || reporting) return;
    setReporting(true);
    setReportError(null);
    try {
      await reportMessage(id);
      setReported(true);
      setShowReportModal(true);
    } catch (err) {
      setReportError(err instanceof ApiError ? err.message : "신고 처리에 실패했습니다.");
    } finally {
      setReporting(false);
    }
  };

  const handleDeleteConfirmed = async () => {
    if (!id) return;
    setDeleting(true);
    setDeleteError(null);
    try {
      await deleteMessage(id);
      navigate("/");
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

  if (error || !message) {
    return (
      <div className="bg-danger-bg text-danger-text rounded-2xl p-6 text-center">
        <p className="font-medium mb-1">에러가 발생했습니다</p>
        <p className="text-sm">{error ?? "해당 기록을 찾을 수 없습니다."}</p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <Alert verdict={message.verdict} />

      <div className="bg-white rounded-2xl p-4 shadow-[0_6px_16px_rgba(15,17,21,0.06)]">
        <p className="text-xs text-muted mb-1">사용자 수신 문자</p>
        <p className="font-medium text-ink">{message.content}</p>
      </div>

      {message.reason && (
        <div className="bg-white rounded-2xl p-4 shadow-[0_6px_16px_rgba(15,17,21,0.06)] space-y-2">
          <p className="text-xs text-muted mb-1">판별 근거</p>
          <p className="text-sm"><span className="font-medium">공식 데이터:</span> {message.reason.officialData}</p>
          <p className="text-sm"><span className="font-medium">위험 요소:</span> {message.reason.riskFactor}</p>
        </div>
      )}

      {deleteError && (
        <div className="bg-danger-bg text-danger-text rounded-2xl p-3.5 text-sm text-center">{deleteError}</div>
      )}
      {reportError && (
        <div className="bg-danger-bg text-danger-text rounded-2xl p-3.5 text-sm text-center">{reportError}</div>
      )}

      <div className="flex gap-3 pt-1">
        <Button variant="danger" onClick={() => setShowDeleteConfirm(true)}>삭제하기</Button>
        <Button variant="secondary" onClick={handleReport} disabled={reported || reporting}>
          {reporting ? "처리 중..." : reported ? "신고 완료" : "신고하기"}
        </Button>
      </div>

      <Modal open={showDeleteConfirm} onClose={() => !deleting && setShowDeleteConfirm(false)}>
        <div className="flex flex-col items-center text-center gap-3">
          <div className="w-12 h-12 rounded-full bg-danger-bg text-danger-text flex items-center justify-center">
            <Trash2 size={22} />
          </div>
          <div>
            <p className="font-semibold text-ink">이 기록을 삭제할까요?</p>
            <p className="text-sm text-muted mt-1">삭제하면 다시 되돌릴 수 없어요.</p>
          </div>
          <div className="flex gap-2 w-full mt-1">
            <button onClick={() => setShowDeleteConfirm(false)} disabled={deleting} className="flex-1 py-2.5 rounded-xl bg-gray-100 text-ink text-sm font-medium">
              취소
            </button>
            <button onClick={handleDeleteConfirmed} disabled={deleting} className="flex-1 py-2.5 rounded-xl bg-danger text-white text-sm font-medium disabled:opacity-70">
              {deleting ? "삭제 중..." : "삭제"}
            </button>
          </div>
        </div>
      </Modal>

      <Modal open={showReportModal} onClose={() => setShowReportModal(false)}>
        <div className="flex flex-col items-center text-center gap-3">
          <div className="w-12 h-12 rounded-full bg-safe-bg text-safe-text flex items-center justify-center">
            <CheckCircle2 size={22} />
          </div>
          <div>
            <p className="font-semibold text-ink">신고가 접수되었습니다</p>
            <p className="text-sm text-muted mt-1">소중한 제보 감사합니다. 검토 후 반영할게요.</p>
          </div>
          <button onClick={() => setShowReportModal(false)} className="w-full py-2.5 rounded-xl bg-brand text-white text-sm font-medium mt-1">
            확인
          </button>
        </div>
      </Modal>
    </div>
  );
}