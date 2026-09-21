// In-memory + localStorage filesystem mock for browser preview

const STORE_PREFIX = "narada_fs:";

function storeKey(p: string) { return STORE_PREFIX + p; }

export function existsSync(p: string): boolean {
    return localStorage.getItem(storeKey(p)) !== null;
}

export function readTextFileSync(p: string): string {
    return localStorage.getItem(storeKey(p)) ?? "";
}

export function writeTextFileSync(p: string, data: string): void {
    localStorage.setItem(storeKey(p), data);
}

export function mkdirSync(p: string): void {
    // no-op, flat storage
}

export function truncateSync(p: string, _len?: number): void {
    localStorage.setItem(storeKey(p), "");
}

export async function create(_p: string) {
    let data = "";
    return {
        write(bytes: Uint8Array) {
            data = new TextDecoder().decode(bytes);
            return Promise.resolve();
        },
        close() {
            writeTextFileSync(_p, data);
            return Promise.resolve();
        },
    };
}

export async function writeTextFile(p: string, data: string) {
    writeTextFileSync(p, data);
}

export async function readTextFile(p: string): Promise<string> {
    return readTextFileSync(p);
}

export async function exists(p: string): Promise<boolean> {
    return existsSync(p);
}

export async function truncate(p: string, _len?: number): Promise<void> {
    truncateSync(p);
}

export async function mkdir(_p: string): Promise<void> {
    mkdirSync(_p);
}

export const BaseDirectory = {
    Download: 11,
    Home: 1,
};
