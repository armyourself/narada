const SEP = "/";

function join(...parts: string[]): string {
    return parts
        .join(SEP)
        .replace(/\/+/g, SEP)
        .replace(/\/$/, "");
}

async function homeDir(): Promise<string> {
    return "/home/mock";
}

export { join, homeDir };
