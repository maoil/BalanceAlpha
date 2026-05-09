import type { InputHTMLAttributes } from "react";
import { CalendarDays } from "lucide-react";

type DateFieldProps = Omit<InputHTMLAttributes<HTMLInputElement>, "type">;

export function DateField({ className, ...props }: DateFieldProps) {
  return (
    <span className={["date-field", className].filter(Boolean).join(" ")}>
      <input {...props} type="date" />
      <CalendarDays aria-hidden="true" className="date-field-icon" focusable="false" />
    </span>
  );
}
