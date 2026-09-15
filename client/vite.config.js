import { defineConfig } from "vite";
import { sveltekit } from "@sveltejs/kit/vite";
import path from "path";

var inTauri = !!process.env.TAURI_PLATFORM;

function resolveTauri(pkg) {
    return inTauri ? pkg : path.resolve("src/lib/mocks", pkg + ".ts");
}

export default defineConfig(async () => ({
  plugins: [sveltekit()],

  resolve: {
    alias: {
      "@tauri-apps/api/window":               resolveTauri("tauri-api-window"),
      "@tauri-apps/api/path":                 resolveTauri("tauri-api-path"),
      "@tauri-apps/plugin-fs":                resolveTauri("tauri-plugin-fs"),
      "@tauri-apps/plugin-notification":      resolveTauri("tauri-plugin-notification"),
      "@tauri-apps/plugin-autostart":         resolveTauri("tauri-plugin-autostart"),
      "@tauri-apps/plugin-os":                resolveTauri("tauri-plugin-os"),
      "@tauri-apps/plugin-process":           resolveTauri("tauri-plugin-process"),
    },
  },

  clearScreen: false,
  server: {
    port: 1420,
    strictPort: true,
    watch: {
      ignored: ["**/src-tauri/**"],
    },
  },
}));
