import DOMPurify from "dompurify";

/** Escape text for safe interpolation into HTML. */
export function escapeHtml(text: string): string {
    return text
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#39;");
}

/**
 * Heuristic: does this body contain anything that looks like an HTML tag?
 * Plain-text bodies (including the server-side sanitized list previews and
 * Nostr records) fail this check and are rendered escaped instead.
 */
export function looksLikeHtml(body: string): boolean {
    return /<[a-z/!][^>]*>/i.test(body);
}

/**
 * Sanitize an email body for rendering inside the sandboxed iframe.
 *
 * Scripts and event handlers are stripped (DOMPurify defaults), while
 * iframes, video and audio — which user mail legitimately embeds — are
 * explicitly kept, with `src` still validated against safe URL schemes.
 */
export function sanitizeEmailHtml(html: string): string {
    return DOMPurify.sanitize(html, {
        ADD_TAGS: ["iframe", "video", "audio", "source", "track", "picture"],
        ADD_ATTR: [
            "src",
            "controls",
            "preload",
            "loop",
            "muted",
            "autoplay",
            "playsinline",
            "allow",
            "allowfullscreen",
            "allowtransparency",
            "frameborder",
            "scrolling",
            "width",
            "height",
            "target",
            "rel",
            "poster",
            "sandbox",
        ],
    });
}

const HEIGHT_SCRIPT = `<script>(function(){
function send(){try{parent.postMessage({type:'narada:email-height',h:document.documentElement.scrollHeight},'*')}catch(e){}}
window.addEventListener('load',send);
window.addEventListener('resize',send);
if(window.ResizeObserver){new ResizeObserver(send).observe(document.documentElement)}
send();
})();</script>`;

/**
 * Build the full srcdoc document for an email body: isolated typography
 * (so the app's CSS reset cannot flatten the email), dark-scheme defaults
 * matching the reading pane, and a tiny script reporting content height so
 * the parent iframe can size itself.
 */
export function buildEmailSrcDoc(body: string): string {
    const content = looksLikeHtml(body)
        ? sanitizeEmailHtml(body)
        : `<pre class="narada-plain">${escapeHtml(body)}</pre>`;

    return `<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
html,body{margin:0;padding:0;background:transparent;}
body{font-family:'Segoe UI',system-ui,sans-serif;font-size:14px;line-height:1.55;color:#d3d3d3;word-break:break-word;overflow-wrap:break-word;}
img,video{max-width:100%;height:auto;}
audio{max-width:100%;}
a{color:#4a9eff;}
table{max-width:100%;border-collapse:collapse;}
td,th{padding:4px 8px;}
blockquote{border-left:3px solid #444;margin:8px 0 8px 8px;padding-left:10px;color:#9b9b9b;}
pre.narada-plain{white-space:pre-wrap;word-break:break-word;font-family:inherit;margin:0;}
h1,h2,h3,h4{line-height:1.3;}
</style></head><body>${content}${HEIGHT_SCRIPT}</body></html>`;
}
