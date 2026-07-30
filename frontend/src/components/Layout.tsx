import BottomNav from "./BottomNav";
import Onboarding from "./Onboarding";

export default function Layout({ children }: { children: React.ReactNode }) {
  return (
    <div className="h-screen bg-gray-200 flex justify-center">
      <div className="w-full max-w-md h-full bg-paper flex flex-col shadow-xl overflow-hidden">
        <header className="bg-paper px-5 py-4 border-b border-gray-200 shrink-0">
          <h1 className="text-xl font-semibold text-ink">스미싱 탐지</h1>
        </header>
        <main className="flex-1 overflow-y-auto px-4 py-4">{children}</main>
        <Onboarding />
        <BottomNav />
      </div>
    </div>
  );
}