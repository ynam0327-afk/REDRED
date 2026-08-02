import { useState, useEffect, useCallback } from "react";
import type { Message } from "../types";
import { getMessages } from "../api/smishing";
import { adaptMessage } from "../utils/adapt";

export function useMessages() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const raw = await getMessages();
      setMessages(raw.map(adaptMessage));
    } catch (err) {
      setError("데이터를 불러오지 못했습니다. 서버 연결을 확인해주세요.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
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
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const addMessage = (newMessage: Message) => {
    setMessages((prev) => [newMessage, ...prev]);
  };
  const reportMessage = (id: string) => {
    setMessages((prev) => prev.map((m) => (m.id === id ? { ...m, reported: true } : m)));
  };
  const deleteMessage = (id: string) => {
    setMessages((prev) => prev.filter((m) => m.id !== id));
  };
  const removeMessages = (ids: string[]) => {
    const idSet = new Set(ids);
    setMessages((prev) => prev.filter((m) => !idSet.has(m.id)));
  };
  const clearAllMessages = () => {
    setMessages([]);
  };

  return { messages, loading, error, refetch: load, addMessage, reportMessage, deleteMessage, removeMessages, clearAllMessages };
}