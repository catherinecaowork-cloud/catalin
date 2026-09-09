import { forwardRef, type InputHTMLAttributes } from "react";

import { cn } from "./cn";

type Props = InputHTMLAttributes<HTMLInputElement> & {
  invalid?: boolean;
};

export const Input = forwardRef<HTMLInputElement, Props>(function Input(
  { className, invalid, type = "text", ...rest },
  ref,
) {
  return (
    <input
      ref={ref}
      type={type}
      className={cn(invalid && "invalid", className)}
      {...rest}
    />
  );
});
