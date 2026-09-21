/**
 * Design tokens — single source of truth for the UI design system.
 *
 * When the frontend.html mockup changes, update the values here.
 * Components import from this module instead of hardcoding CSS values.
 *
 * Usage in Svelte:
 *   import { tokens } from "$lib/ui/tokens";
 *   <div style="font-family: {tokens.font.ui}; font-size: {tokens.font.md};">
 */

export const tokens = {
    /** Color palette — maps directly to CSS custom properties. */
    colors: {
        cream: "#FFFBF7",
        ink: "#453B35",
        inkDim: "#8F8177",
        inkFaint: "#BDB0A5",
        accent: "#C99B76",
        accentSoft: "#E7C7A8",
        direct: "#4C7A61",
        relay: "#A97635",
        gateway: "#7C6A5E",
    },

    /** Glass morphism surface colors. */
    glass: {
        base: "rgba(255,255,255,0.50)",
        strong: "rgba(255,255,255,0.72)",
        solid: "rgba(255,255,255,0.88)",
        border: "rgba(255,255,255,0.65)",
    },

    /** Typography. */
    font: {
        ui: "'Space Grotesk', sans-serif",
        body: "'Inter', sans-serif",
        xs: "0.72rem",
        sm: "0.84rem",
        md: "0.92rem",
        lg: "1.1rem",
        xl: "1.3rem",
        x2l: "1.6rem",
    },

    /** Spacing scale. */
    spacing: {
        x2s: "0.25rem",
        xs: "0.5rem",
        sm: "0.75rem",
        md: "1rem",
        lg: "1.5rem",
        xl: "2rem",
        x2l: "3rem",
    },

    /** Border radius. */
    radius: {
        base: "24px",
        sm: "12px",
    },

    /** Layout dimensions. */
    layout: {
        railWidth: "74px",
        menuWidth: "250px",
        menuWidthCollapsed: "0px",
        listPanelWidth: "330px",
        composeWidth: "420px",
        titlebarHeight: "30px",
        titlebarRadius: "18px",
    },
} as const;

/** Dark theme overrides — applied when html[data-color-scheme="dark"]. */
export const darkTokens = {
    colors: {
        cream: "#1B1917",
        ink: "#EFE7E0",
        inkDim: "#B0A399",
        inkFaint: "#726558",
        accent: "#E3B487",
        accentSoft: "#C99B76",
        direct: "#7FB89D",
        relay: "#D9A257",
        gateway: "#B0A090",
    },
    glass: {
        base: "rgba(255,255,255,0.06)",
        strong: "rgba(255,255,255,0.09)",
        solid: "rgba(30,27,24,0.75)",
        border: "rgba(255,255,255,0.12)",
    },
} as const;
