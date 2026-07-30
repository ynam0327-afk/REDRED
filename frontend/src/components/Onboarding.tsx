import { useState, useEffect } from "react";
import { ShieldCheck, Radio, Bell } from "lucide-react";
import Modal from "./Modal";

const STEPS = [
  { icon: <ShieldCheck size={28} />, title: "의심 문자를 바로 확인", desc: "받은 문자를 붙여넣으면 위험도를 즉시 분석해드려요." },
  { icon: <Radio size={28} />, title: "실시간 재난 현황", desc: "행정안전부·소방청의 공식 재난 정보를 한눈에 볼 수 있어요." },
  { icon: <Bell size={28} />, title: "권한 설정은 나중에", desc: "설정 탭에서 알림·위치 권한을 언제든 켜고 끌 수 있어요." },
];

export default function Onboarding() {
  const [open, setOpen] = useState(false);
  const [step, setStep] = useState(0);

  useEffect(() => {
    if (!localStorage.getItem("onboarded")) setOpen(true);
  }, []);

  const close = () => {
    localStorage.setItem("onboarded", "1");
    setOpen(false);
  };

  const current = STEPS[step];

  return (
    <Modal open={open} onClose={close}>
      <div className="flex flex-col items-center text-center gap-3">
        <div className="w-14 h-14 rounded-2xl bg-brand-bg text-brand flex items-center justify-center">{current.icon}</div>
        <div>
          <p className="font-semibold text-ink">{current.title}</p>
          <p className="text-sm text-muted mt-1">{current.desc}</p>
        </div>
        <div className="flex gap-1.5 my-1">
          {STEPS.map((_, i) => (
            <span key={i} className={`w-1.5 h-1.5 rounded-full ${i === step ? "bg-brand" : "bg-gray-200"}`} />
          ))}
        </div>
        <button
          onClick={() => (step < STEPS.length - 1 ? setStep(step + 1) : close())}
          className="w-full py-2.5 rounded-xl bg-brand text-white text-sm font-medium"
        >
          {step < STEPS.length - 1 ? "다음" : "시작하기"}
        </button>
      </div>
    </Modal>
  );
}