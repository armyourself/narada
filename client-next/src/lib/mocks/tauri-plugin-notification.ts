export async function isPermissionGranted(): Promise<boolean> {
    return true;
}

export async function requestPermission(): Promise<string> {
    return "granted";
}

export function sendNotification(_opts: { title: string; body?: string }) {
    console.log("[browser-mock] notification:", _opts.title);
}
