import type { InputHTMLAttributes, ReactNode } from "react";

type Props = Omit<InputHTMLAttributes<HTMLInputElement>, "type"> & {
  label: ReactNode;
};

export function Checkbox({ label, className, ...rest }: Props) {
  return (
    <label className={className ?? "check"}>
      <input type="checkbox" {...rest} />
      {label}
    </label>
  );
}
