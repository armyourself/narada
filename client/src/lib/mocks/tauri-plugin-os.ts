export async function locale(): Promise<string> {
    return navigator.language || "en-US";
}
