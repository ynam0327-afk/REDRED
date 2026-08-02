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
  return { messages, loading, error };
}
