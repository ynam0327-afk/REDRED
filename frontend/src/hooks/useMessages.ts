import { useState, useEffect } from "react";
import type { Message } from "../types";
import { getMessages, analyzeMessage } from "../api/smishing";
import { adaptMessage } from "../utils/adapt";

export function useMessages() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [analyzing, setAnalyzing] = useState(false);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const raw = await getMessages();
        if (!cancelled) setMessages(raw.map(adaptMessage));
      } catch (err) {
        if (!cancelled) setError("데이터를 불러오지 못했습니다. 서버 연결을 확인해주세요.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, []);

  // 기존 addMessage(로컬 상태만 바꾸던 것)를 실제 서버 호출로 교체
  const analyze = async (text: string) => {
    setAnalyzing(true);
    try {
      const raw = await analyzeMessage(text);
      const adapted = adaptMessage(raw);
      setMessages((prev) => [adapted, ...prev]);
      return adapted;
    } catch (err) {
      setError("분석에 실패했습니다. 잠시 후 다시 시도해주세요.");
      throw err;
    } finally {
      setAnalyzing(false);
    }
  };

  const reportMessage = (id: string) => {
    setMessages((prev) => prev.map((m) => (m.id === id ? { ...m, reported: true } : m)));
  };

  const deleteMessage = (id: string) => {
    setMessages((prev) => prev.filter((m) => m.id !== id));
  };

  return { messages, loading, error, analyzing, analyze, reportMessage, deleteMessage };
}
