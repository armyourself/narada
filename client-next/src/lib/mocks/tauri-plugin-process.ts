export async function exit(_code?: number): Promise<void> {
    console.log("[browser-mock] exit called, no-op in browser");
}

export async function relaunch(): Promise<void> {
    console.log("[browser-mock] relaunch called, no-op in browser");
}
