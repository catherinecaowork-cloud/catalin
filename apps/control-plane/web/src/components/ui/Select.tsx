import { forwardRef, type SelectHTMLAttributes } from "react";

import { cn } from "./cn";

type Props = SelectHTMLAttributes<HTMLSelectElement>;

export const Select = forwardRef<HTMLSelectElement, Props>(function Select(
  { className, ...rest },
  ref,
) {
  return <select ref={ref} className={cn(className)} {...rest} />;
});
