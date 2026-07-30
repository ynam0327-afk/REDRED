import { NavLink } from "react-router-dom";
import { ShieldCheck, Radio, Settings } from "lucide-react";

const TABS = [
  { to: "/", label: "탐지함", icon: ShieldCheck },
  { to: "/feed", label: "재난현황", icon: Radio },
  { to: "/settings", label: "설정", icon: Settings },
];

export default function BottomNav() {
  return (
    <nav className="shrink-0 bg-white border-t border-gray-100 flex justify-around py-2">
      {TABS.map(({ to, label, icon: Icon }) => (
        <NavLink key={to} to={to} className="flex flex-col items-center gap-0.5 px-4 py-1">
          {({ isActive }) => (
            <>
              <Icon size={20} color={isActive ? "#5B5BF6" : "#B5B7C0"} strokeWidth={isActive ? 2.2 : 1.8} />
              <span className={`text-[11px] ${isActive ? "font-medium text-brand" : "text-gray-400"}`}>{label}</span>
            </>
          )}
        </NavLink>
      ))}
    </nav>
  );
}