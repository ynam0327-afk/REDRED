import type { Verdict } from "../types";

const STYLES: Record<Verdict, string> = {
  danger: "bg-danger-bg text-danger-text",
  safe: "bg-safe-bg text-safe-text",
  neutral: "bg-neutral-bg text-neutral-text",
};

const LABEL: Record<Verdict, string> = {
  danger: "위험",
  safe: "안전",
  neutral: "일반",
};

export default function Badge({ verdict }: { verdict: Verdict }) {
  return (
    <span className={`px-2.5 py-1 rounded-full text-xs font-bold ${STYLES[verdict]}`}>
      {LABEL[verdict]}
    </span>
  );
}