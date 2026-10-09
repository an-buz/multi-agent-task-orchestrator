"use client";

import { useState } from "react";
import { LoaderCircle, Trash2 } from "lucide-react";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogMedia,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";

export function DeleteConfirmationDialog({ name, entity, description, pending, onClose, onConfirm }: {
  name: string; entity: "agent" | "workflow" | "run"; description?: string; pending: boolean;
  onClose: () => void; onConfirm: () => Promise<void>;
}) {
  const [error, setError] = useState("");
  async function confirm() {
    setError("");
    try {
      await onConfirm();
      onClose();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : `Could not delete the ${entity}.`);
    }
  }
  return <AlertDialog open onOpenChange={(open) => { if (!open && !pending) onClose(); }}>
    <AlertDialogContent>
      <AlertDialogHeader>
        <AlertDialogMedia className="bg-destructive/10 ring-1 ring-destructive/20"><Trash2 className="text-destructive" /></AlertDialogMedia>
        <AlertDialogTitle>Delete {entity}?</AlertDialogTitle>
        <AlertDialogDescription>
          This will permanently delete “{name}”. This action cannot be undone.
          {description && <> {description}</>}
        </AlertDialogDescription>
      </AlertDialogHeader>
      {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
      <AlertDialogFooter>
        <AlertDialogCancel disabled={pending}>Cancel</AlertDialogCancel>
        <AlertDialogAction variant="destructive" disabled={pending} onClick={() => void confirm()}>
          {pending ? <LoaderCircle data-icon="inline-start" className="animate-spin" /> : <Trash2 data-icon="inline-start" />}
          {pending ? "Deleting…" : `Delete ${entity}`}
        </AlertDialogAction>
      </AlertDialogFooter>
    </AlertDialogContent>
  </AlertDialog>;
}
