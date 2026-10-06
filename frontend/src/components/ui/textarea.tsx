import * as React from "react";

import { cn } from "@/lib/utils";

function Textarea({ className, ...props }: React.ComponentProps<"textarea">) {
  return (
    <textarea
      className={cn(
        "flex min-h-15 w-full resize-y bg-transparent px-3 py-2 text-sm placeholder:text-muted outline-none disabled:cursor-not-allowed disabled:opacity-50 dark",
        "[&::-webkit-scrollbar]:hidden",
        "[&::-webkit-scrollbar-thumb]:rounded-full",
        "[&::-webkit-scrollbar-thumb]:bg-transparent",
        "border border-(--border) bg-[#050816] text-slate-200 placeholder:text-slate-600 focus:border-emerald-500/60 rounded-lg leading-6",
        className,
      )}
      {...props}
    />
  );
}

export { Textarea };
