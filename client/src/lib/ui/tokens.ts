/**
 * Design tokens -- single source of truth for the UI design system.
 * Matches the Notion Mail frontend.html mockup.
 *
 * Components import from this module instead of hardcoding CSS values.
 */

export const tokens = {
    colors: {
        sidebar: "#f7f7f5",
        hover: "#efefed",
        active: "#e8e8e6",
        border: "#e6e6e3",
        text: "#37352f",
        textMuted: "#84827e",
    },
    glass: {
        base: "transparent",
        strong: "transparent",
        solid: "transparent",
        border: "transparent",
    },
    font: {
        sans: "'Inter', sans-serif",
        xs: "0.6875rem",
        sm: "0.8125rem",
        md: "0.875rem",
        lg: "1rem",
        xl: "1.25rem",
    },
    spacing: {
        xs: "0.25rem",
        sm: "0.5rem",
        md: "0.75rem",
        lg: "1rem",
        xl: "1.5rem",
        xxl: "2rem",
    },
    radius: {
        sm: "6px",
        md: "8px",
        lg: "12px",
    },
    layout: {
        sidebarWidth: "256px",
        threadPaneWidth: "620px",
        threadPaneWidthLg: "700px",
    },
} as const;

export const darkTokens = {
    colors: {
        sidebar: "#191919",
        hover: "#262626",
        active: "#2f2f2f",
        border: "#2a2a2a",
        text: "#e0e0e0",
        textMuted: "#84827e",
    },
    glass: {
        base: "transparent",
        strong: "transparent",
        solid: "transparent",
        border: "transparent",
    },
} as const;
