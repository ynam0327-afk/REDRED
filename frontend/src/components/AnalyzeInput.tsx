import { useState } from "react";
import { Send, Loader2 } from "lucide-react";

interface AnalyzeInputProps {
  onAnalyze: (text: string) => void;
  pending?: boolean;
}

export default function AnalyzeInput({ onAnalyze, pending }: AnalyzeInputProps) {
  const [text, setText] = useState("");

  const handleSubmit = () => {
    if (!text.trim() || pending) return;
    onAnalyze(text);
    setText("");
  };

  return (
    <div className="bg-white rounded-2xl p-4 mb-4 shadow-[0_8px_20px_rgba(91,91,246,0.10)]">
      <p className="text-sm font-medium mb-2 text-ink">의심되는 문자를 붙여넣어보세요</p>
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder="문자 내용을 여기에 붙여넣으세요..."
        className="w-full bg-gray-50 rounded-xl p-3 text-sm resize-none h-24 focus:outline-none focus:ring-2 focus:ring-brand"
      />
      <button
        onClick={handleSubmit}
        disabled={pending}
        className="mt-3 w-full bg-brand text-white rounded-2xl py-3 font-medium text-sm flex items-center justify-center gap-1.5 shadow-[0_3px_0_0_#3E3ECF] active:translate-y-[2px] active:shadow-[0_1px_0_0_#3E3ECF] transition disabled:opacity-70"
      >
        {pending ? <Loader2 size={16} className="animate-spin" /> : <Send size={16} />}
        {pending ? "분석 중..." : "분석하기"}
      </button>
    </div>
  );
}