"use client";

import { useEffect } from "react";
import { useUiStore, closeConfirm } from "@/lib/stores/ui";
import { local } from "@/lib/locales";
import { DEFAULT_LANGUAGE } from "@/lib/constants";

export default function ConfirmDialog() {
    const confirm = useUiStore((s) => s.confirm);

    useEffect(() => {
        if (!confirm) return;
        const onKey = (event: KeyboardEvent) => {
            if (event.key === "Escape") {
                void confirm.onCancel?.();
                closeConfirm();
            }
        };
        window.addEventListener("keydown", onKey);
        return () => window.removeEventListener("keydown", onKey);
    }, [confirm]);

    if (!confirm) return null;

    const onConfirm = async () => {
        await confirm.onConfirm();
        closeConfirm();
    };

    const onCancel = async () => {
        await confirm.onCancel?.();
        closeConfirm();
    };

    return (
        <div className="modal confirm">
            <div className="confirm-card">
                <h3>{confirm.title}</h3>
                {confirm.details && <p dangerouslySetInnerHTML={{ __html: confirm.details }} />}
                <div className="confirm-actions">
                    <button type="button" className="btn btn-outline" onClick={() => void onCancel()}>
                        {confirm.cancelText || local.cancel[DEFAULT_LANGUAGE]}
                    </button>
                    <button type="button" className="btn btn-cta" onClick={() => void onConfirm()}>
                        {confirm.confirmText}
                    </button>
                </div>
            </div>
        </div>
    );
}
