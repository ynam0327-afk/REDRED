interface ButtonProps {
  children: React.ReactNode;
  onClick?: () => void;
  variant?: "primary" | "secondary" | "danger";
  disabled?: boolean;
}

const VARIANTS = {
  primary: "bg-brand text-white shadow-[0_3px_0_0_#3E3ECF] active:translate-y-[2px] active:shadow-[0_1px_0_0_#3E3ECF]",
  secondary: "bg-gray-100 text-ink hover:bg-gray-200",
  danger: "bg-danger text-white shadow-[0_3px_0_0_#A32D2D] active:translate-y-[2px] active:shadow-[0_1px_0_0_#A32D2D]",
};

export default function Button({ children, onClick, variant = "primary", disabled }: ButtonProps) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className={`px-5 py-2.5 rounded-2xl font-medium text-sm transition disabled:opacity-60 ${VARIANTS[variant]}`}
    >
      {children}
    </button>
  );
}