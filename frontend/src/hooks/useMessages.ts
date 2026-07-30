import { useState, useEffect } from "react";
import type { Message } from "../types";
import { getMessages } from "../api/smishing";
import { adaptMessage } from "../utils/adapt";

export function useMessages() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

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

  // 로컬에서 임시로 추가/신고/삭제하는 기능은 그대로 유지 (POST 연동 전까지)
  const addMessage = (newMessage: Message) => {
    setMessages((prev) => [newMessage, ...prev]);
  };
  const reportMessage = (id: string) => {
    setMessages((prev) => prev.map((m) => (m.id === id ? { ...m, reported: true } : m)));
  };
  const deleteMessage = (id: string) => {
    setMessages((prev) => prev.filter((m) => m.id !== id));
  };

  return { messages, loading, error, addMessage, reportMessage, deleteMessage };
}