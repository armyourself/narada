import { create } from "zustand";
import { generateRandomId } from "@/lib/utils";

export interface MessageProps {
    title: string;
    details?: string;
    onCloseText?: string;
    onClose?: () => void | Promise<void>;
}

export interface ToastProps {
    content: string;
    autoCloseDelay?: number;
    onUndo?: () => void | Promise<void>;
}

export interface ToastItem extends ToastProps {
    id: string;
}

export interface ComposePrefill {
    to?: string;
    subject?: string;
    body?: string;
}

export interface ConfirmProps {
    title: string;
    details?: string;
    confirmText: string;
    cancelText?: string;
    onConfirm: () => void | Promise<void>;
    onCancel?: () => void | Promise<void>;
}

interface UiState {
    message: MessageProps | null;
    toasts: ToastItem[];
    compose: ComposePrefill | null;
    paletteOpen: boolean;
    confirm: ConfirmProps | null;
    settingsOpen: boolean;
}

export const useUiStore = create<UiState>(() => ({
    message: null,
    toasts: [],
    compose: null,
    paletteOpen: false,
    confirm: null,
    settingsOpen: false,
}));

export function show(props: MessageProps): void {
    if (useUiStore.getState().message) return;
    useUiStore.setState({ message: props });
}

export async function close(): Promise<void> {
    const message = useUiStore.getState().message;
    if (message?.onClose) await message.onClose();
    useUiStore.setState({ message: null });
}

export function showToast(props: ToastProps): void {
    const id = generateRandomId();
    useUiStore.setState({ toasts: [...useUiStore.getState().toasts, { ...props, id }] });
    setTimeout(() => closeToast(id), props.autoCloseDelay ?? 3000);
}

export function closeToast(id: string): void {
    useUiStore.setState({ toasts: useUiStore.getState().toasts.filter((t) => t.id !== id) });
}

export function openCompose(prefill: ComposePrefill = {}): void {
    useUiStore.setState({ compose: prefill });
}

export function closeCompose(): void {
    useUiStore.setState({ compose: null });
}

export function openPalette(): void {
    useUiStore.setState({ paletteOpen: true });
}

export function closePalette(): void {
    useUiStore.setState({ paletteOpen: false });
}

export function showConfirm(props: ConfirmProps): void {
    if (useUiStore.getState().confirm) return;
    useUiStore.setState({ confirm: props });
}

export function closeConfirm(): void {
    useUiStore.setState({ confirm: null });
}

export function openSettings(): void {
    useUiStore.setState({ settingsOpen: true });
}

export function closeSettings(): void {
    useUiStore.setState({ settingsOpen: false });
}
