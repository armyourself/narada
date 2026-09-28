import type { NextConfig } from "next";
import path from "node:path";

// Tauri 2 sets TAURI_ENV_PLATFORM for hooks; TAURI_PLATFORM kept as a fallback.
const inTauri = !!(process.env.TAURI_ENV_PLATFORM || process.env.TAURI_PLATFORM);

/** Absolute path of the backend package, used by "Start local server" (Layer 2). */
const nodeDir = path.resolve(process.cwd(), "../node");

/** Bundles the browser mocks instead of the real Tauri runtime outside Tauri. */
function mock(pkg: string) {
  // Turbopack's resolveAlias does not accept Windows absolute paths.
  return `./src/lib/mocks/${pkg}.ts`;
}

const nextConfig: NextConfig = {
  // Tauri serves a local static build — no Node server, SSR, or API routes.
  output: "export",
  env: { NEXT_PUBLIC_NODE_DIR: nodeDir },
  ...(!inTauri && {
    turbopack: {
      resolveAlias: {
        "@tauri-apps/api/window": mock("tauri-api-window"),
        "@tauri-apps/api/path": mock("tauri-api-path"),
        "@tauri-apps/plugin-fs": mock("tauri-plugin-fs"),
        "@tauri-apps/plugin-notification": mock("tauri-plugin-notification"),
        "@tauri-apps/plugin-autostart": mock("tauri-plugin-autostart"),
        "@tauri-apps/plugin-os": mock("tauri-plugin-os"),
        "@tauri-apps/plugin-process": mock("tauri-plugin-process"),
      },
    },
  }),
};

export default nextConfig;
