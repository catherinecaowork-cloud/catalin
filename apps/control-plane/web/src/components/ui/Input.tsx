import { forwardRef, type InputHTMLAttributes } from "react";

import { cn } from "./cn";

type Props = InputHTMLAttributes<HTMLInputElement> & {
  invalid?: boolean;
};

export const Input = forwardRef<HTMLInputElement, Props>(function Input(
  { className, invalid, ...rest },
  ref,
) {
  return (
    <input
      ref={ref}
      className={cn(invalid && "invalid", className)}
      {...rest}
    />
  );
});
