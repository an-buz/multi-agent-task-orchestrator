import * as React from "react";

import { cn } from "@/lib/utils";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 rounded-lg transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500/60 focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50",
  {
    variants: {
      variant: {
        default: "bg-emerald-500 text-slate-950 font-semibold hover:bg-emerald-400",
        secondary:
          "border border-dashed border-slate-700 bg-transparent text-slate-400 hover:border-slate-500 hover:text-slate-200",
        ghost: "bg-transparent text-slate-400 hover:bg-white/5 hover:text-slate-200",
        danger: "bg-red-600 text-white font-semibold hover:bg-red-500",
      },
      size: {
        default: "h-10 px-4 py-2.5 text-sm",
        sm: "h-9 px-3 text-xs",
        lg: "h-11 px-6 text-base font-bold",
        icon: "size-10 p-1",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  },
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

const Button = React.forwardRef<
  HTMLButtonElement,
  ButtonProps
>(
  (
    { className, variant, size, asChild = false, ...props },
    ref,
  ) => {
    const Component = asChild ? Slot : "button";

    return (
      <Component
        ref={ref}
        className={cn(buttonVariants({ variant, size, className }))}
        {...props}
      />
    );
  },
);
Button.displayName = "Button";

export { Button, buttonVariants };
