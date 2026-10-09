import type { RunStatus } from "@/features/runs/types";

const tones: Record<RunStatus, string> = {
  PENDING: "var(--status-pending)",
  PLANNING: "var(--status-progress)",
  AWAITING_CONFIRMATION: "var(--status-pending)",
  IN_PROGRESS: "var(--status-progress)",
  COMPLETED: "var(--status-completed)",
  FAILED: "var(--status-failed)",
  CANCELLED: "var(--status-pending)",
};

export function StatusBadge({ status, variant }: { status: RunStatus; variant?: "pipeline" }) {
  if (variant === "pipeline") {
    const tone = status === "COMPLETED" ? "bg-emerald-500/10 text-emerald-400"
      : status === "IN_PROGRESS" || status === "PLANNING" ? "bg-amber-500/15 text-amber-300"
      : status === "FAILED" ? "bg-rose-500/15 text-rose-400" : "bg-slate-700/70 text-slate-400";
    const label = status.toLowerCase().split("_").map((word) => word[0].toUpperCase() + word.slice(1)).join(" ");
    return <span className={`mt-2 inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] font-medium ${tone}`}><i className="size-1.5 rounded-full bg-current" />{label}</span>;
  }
  return <span className="inline-flex items-center gap-1.5 rounded border border-border px-2 py-1 text-[10px] font-medium"
    style={{ color: tones[status] }}><span className="size-1.5 rounded-full bg-current" />{status}</span>;
}
