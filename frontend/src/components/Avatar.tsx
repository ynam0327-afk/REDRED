import type { Verdict } from "../types";

export default function Avatar({ name, verdict }: { name: string; verdict: Verdict }) {
  const initial = name.trim().charAt(0);

  return (
    <div
      className={
        verdict === "danger"
          ? "p-[2px] rounded-full bg-ig-gradient"
          : "p-[2px] rounded-full bg-gray-200"
      }
    >
      <div className="w-11 h-11 rounded-full bg-white flex items-center justify-center">
        <span className="font-bold text-ink">{initial}</span>
      </div>
    </div>
  );
}