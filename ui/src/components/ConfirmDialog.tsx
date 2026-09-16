/**
 * A confirmation for the one action that cannot be undone.
 *
 * Native `<dialog>` so focus trapping, Escape and the backdrop come from the
 * platform rather than from three hundred lines of our own.
 */

import { useEffect, useRef } from "preact/hooks";

import { t } from "../i18n";
import "./ConfirmDialog.css";

interface ConfirmDialogProps {
  open: boolean;
  title: string;
  body: string;
  confirmLabel: string;
  onConfirm: () => void;
  onCancel: () => void;
}

export function ConfirmDialog({
  open,
  title,
  body,
  confirmLabel,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  const ref = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);

  return (
    <dialog class="dialog" ref={ref} onCancel={onCancel} onClose={onCancel}>
      <h2 class="dialog__title">{title}</h2>
      <p class="dialog__body">{body}</p>
      <div class="row dialog__actions">
        <button type="button" class="button button--secondary" onClick={onCancel}>
          {t("common.cancel")}
        </button>
        <button type="button" class="button" onClick={onConfirm}>
          {confirmLabel}
        </button>
      </div>
    </dialog>
  );
}
