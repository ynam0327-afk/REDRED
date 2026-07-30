import { useState, useEffect } from "react";
import { Bell, MapPin, Info, ShieldCheck } from "lucide-react";

export default function SettingsPage() {
  const [notify, setNotify] = useState(false);
  const [location, setLocation] = useState(false);

  useEffect(() => {
    if (typeof Notification !== "undefined") setNotify(Notification.permission === "granted");
    setLocation(localStorage.getItem("locationEnabled") === "1");
  }, []);

  const handleNotifyToggle = async () => {
    if (typeof Notification === "undefined") return;
    if (Notification.permission === "granted") {
      alert("알림 권한은 브라우저 설정에서 직접 꺼주세요.");
      return;
    }
    const result = await Notification.requestPermission();
    setNotify(result === "granted");
  };

  const handleLocationToggle = () => {
    if (location) {
      localStorage.setItem("locationEnabled", "0");
      setLocation(false);
      return;
    }
    navigator.geolocation.getCurrentPosition(
      () => { localStorage.setItem("locationEnabled", "1"); setLocation(true); },
      () => { alert("위치 권한이 거부되었습니다. 브라우저 설정에서 허용해주세요."); }
    );
  };

  return (
    <div className="space-y-4">
      <div>
        <p className="text-xs font-medium text-muted mb-2 px-1">권한 관리</p>
        <div className="bg-white rounded-2xl shadow-[0_6px_16px_rgba(15,17,21,0.06)] divide-y divide-gray-100">
          <ToggleRow icon={<Bell size={18} />} label="재난 알림" desc="긴급 재난문자 발생 시 푸시 알림" checked={notify} onChange={handleNotifyToggle} />
          <ToggleRow icon={<MapPin size={18} />} label="위치 정보" desc="내 지역 맞춤 재난 정보 수신" checked={location} onChange={handleLocationToggle} />
        </div>
      </div>
      <div>
        <p className="text-xs font-medium text-muted mb-2 px-1">앱 정보</p>
        <div className="bg-white rounded-2xl shadow-[0_6px_16px_rgba(15,17,21,0.06)] divide-y divide-gray-100">
          <InfoRow icon={<Info size={18} />} label="버전" value="1.0.0" />
          <InfoRow icon={<ShieldCheck size={18} />} label="데이터 출처" value="소방청 · 행정안전부" />
        </div>
      </div>
    </div>
  );
}

function ToggleRow({ icon, label, desc, checked, onChange }: { icon: React.ReactNode; label: string; desc: string; checked: boolean; onChange: () => void }) {
  return (
    <div className="flex items-center gap-3 p-4">
      <div className="w-9 h-9 rounded-lg bg-brand-bg text-brand flex items-center justify-center shrink-0">{icon}</div>
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-ink">{label}</p>
        <p className="text-xs text-muted mt-0.5">{desc}</p>
      </div>
      <button onClick={onChange} className={`w-11 h-6 rounded-full shrink-0 transition relative ${checked ? "bg-brand" : "bg-gray-200"}`}>
        <span className={`absolute top-0.5 w-5 h-5 rounded-full bg-white transition-transform ${checked ? "translate-x-[22px]" : "translate-x-0.5"}`} />
      </button>
    </div>
  );
}

function InfoRow({ icon, label, value }: { icon: React.ReactNode; label: string; value: string }) {
  return (
    <div className="flex items-center gap-3 p-4">
      <div className="w-9 h-9 rounded-lg bg-gray-100 text-gray-500 flex items-center justify-center shrink-0">{icon}</div>
      <p className="text-sm font-medium text-ink flex-1">{label}</p>
      <p className="text-sm text-muted">{value}</p>
    </div>
  );
}