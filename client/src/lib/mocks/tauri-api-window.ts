export function getCurrentWindow() {
    return {
        onThemeChanged(_cb: (e: { payload: string }) => void) {
            return { unlisten() {} };
        },
        theme() {
            const stored = localStorage.getItem("data-color-scheme");
            return Promise.resolve(stored || "light");
        },
        minimize() {},
        toggleMaximize() {},
        close() {},
    };
}
