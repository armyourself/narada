import { Command } from "@tauri-apps/plugin-shell";
import { homeDir } from "@tauri-apps/api/path";
import { readTextFile } from "@tauri-apps/plugin-fs";
import { ApiService } from "@/lib/services/ApiService";
import { DEFAULT_SERVER_URL } from "@/lib/constants";

const POLL_INTERVAL_MS = 500;
const READY_TIMEOUT_MS = 20000;
const INFO_FILE = "/.narada/etc/uvicorn.info";

/** Absolute path to the backend package, injected by next.config.ts at build/dev time. */
const NODE_DIR = process.env.NEXT_PUBLIC_NODE_DIR ?? "";

const SPAWN_ATTEMPTS: ReadonlyArray<{ name: string; args: string[] }> = [
    { name: "uv", args: ["run", "python", "-m", "src.main", "--port", "8000"] },
    { name: "python", args: ["-m", "src.main", "--port", "8000"] },
];

export function isTauriRuntime(): boolean {
    return typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
}

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

async function isServerUp(url: string): Promise<boolean> {
    try {
        const response = await ApiService.hello(url);
        return !!response?.success;
    } catch {
        return false;
    }
}

/** Last URL= line of uvicorn.info (the file may hold stale blocks from old runs). */
async function readInfoUrl(): Promise<string | null> {
    try {
        const home = await homeDir();
        const content = await readTextFile(`${home}${INFO_FILE}`);
        const urls = [...content.matchAll(/URL=(\S+)/g)];
        return urls.length ? urls[urls.length - 1][1] : null;
    } catch {
        return null;
    }
}

async function probeCandidates(extra?: string | null): Promise<string | null> {
    const candidates = [...new Set([DEFAULT_SERVER_URL, extra].filter((url): url is string => !!url))];
    for (const url of candidates) {
        if (await isServerUp(url)) return url;
    }
    return null;
}

export type StartLocalServerResult = { ok: true; url: string } | { ok: false; error: string };

/**
 * Layer 2 of the server-start flow: reuse an already-running local server if
 * one answers /hello, otherwise spawn the backend non-interactively
 * (`--port 8000`) and poll until it is ready.
 */
export async function startLocalServer(): Promise<StartLocalServerResult> {
    const existing = await probeCandidates(await readInfoUrl());
    if (existing) return { ok: true, url: existing };

    if (!NODE_DIR) return { ok: false, error: "Local server directory is unknown in this build." };

    let lastError = "";
    let spawned = false;
    for (const attempt of SPAWN_ATTEMPTS) {
        try {
            const command = Command.create(attempt.name, [...attempt.args], {
                cwd: NODE_DIR,
            });
            command.addListener("error", (error) => {
                lastError = String(error);
            });
            await command.spawn();
            spawned = true;
            break;
        } catch (error) {
            lastError = String(error);
        }
    }
    if (!spawned) return { ok: false, error: lastError || "Could not launch the server process." };

    const deadline = Date.now() + READY_TIMEOUT_MS;
    while (Date.now() < deadline) {
        await sleep(POLL_INTERVAL_MS);
        const ready = await probeCandidates(await readInfoUrl());
        if (ready) return { ok: true, url: ready };
    }
    return { ok: false, error: "The local server did not become ready in time." };
}
