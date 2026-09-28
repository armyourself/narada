import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Narada",
  description: "Decentralized email with end-to-end encryption",
};

const themeBootstrap = `
(function() {
    var stored = localStorage.getItem('theme');
    var isDark = stored === 'dark' || (!stored && window.matchMedia('(prefers-color-scheme: dark)').matches);
    var scheme = isDark ? 'dark' : 'light';
    document.documentElement.classList.toggle('dark', isDark);
    document.documentElement.setAttribute('data-color-scheme', scheme);
})();
`;

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className="h-full" suppressHydrationWarning>
      <body className="h-full bg-notion-canvas text-notion-text font-sans antialiased overflow-hidden select-none">
        <script id="theme-boot" dangerouslySetInnerHTML={{ __html: themeBootstrap }} />
        {children}
      </body>
    </html>
  );
}
