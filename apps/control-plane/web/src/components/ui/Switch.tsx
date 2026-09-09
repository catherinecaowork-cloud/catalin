import type { InputHTMLAttributes, ReactNode } from "react";

type Props = Omit<InputHTMLAttributes<HTMLInputElement>, "type"> & {
  label: ReactNode;
};

export function Switch({ label, className, ...rest }: Props) {
  return (
    <label className={className ?? "switch"}>
      <input type="checkbox" {...rest} />
      <span className="switch-ui" /> {label}
    </label>
  );
}
