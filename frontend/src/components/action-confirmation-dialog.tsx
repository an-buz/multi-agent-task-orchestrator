"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";

export function ActionConfirmationDialog({
  open,
  onOpenChange,
  title,
  description,
  actionLabel,
  pending = false,
  cancelLabel = "Keep editing",
  onConfirm,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description: string;
  actionLabel: string;
  pending?: boolean;
  cancelLabel?: string;
  onConfirm: () => void;
}) {
  return (
    <AlertDialog
      open={open}
      onOpenChange={(next, details) => {
        if (pending) details.cancel();
        else onOpenChange(next);
      }}
    >
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{title}</AlertDialogTitle>
          <AlertDialogDescription>{description}</AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel disabled={pending}>{cancelLabel}</AlertDialogCancel>
          <AlertDialogAction variant="destructive" disabled={pending} onClick={onConfirm}>
            {actionLabel}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}

export function CancelRunButton({
  pending,
  onConfirm,
}: {
  pending: boolean;
  onConfirm: () => Promise<unknown>;
}) {
  const [open, setOpen] = useState(false);

  return (
    <>
      <Button type="button" variant="destructive" disabled={pending} onClick={() => setOpen(true)}>
        Cancel run
      </Button>
      <ActionConfirmationDialog
        open={open}
        onOpenChange={setOpen}
        pending={pending}
        title="Cancel run?"
        description="A cancelled run cannot be resumed. This action cannot be undone."
        actionLabel="Cancel run"
        cancelLabel="Keep running"
        onConfirm={() => {
          if (pending) return;

          void onConfirm().then(
            () => setOpen(false),
            () => setOpen(false),
          );
        }}
      />
    </>
  );
}
