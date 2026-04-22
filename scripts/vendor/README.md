# Vendor Assets

Place `mermaid.min.js` in this directory to enable fully local roadmap rendering in `scripts/named_agent_dashboard.html`.

`mermaid.min.js` is now included in this repository for air-gapped roadmap rendering.

Download command (run from repository root):

```bash
curl -L "https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js" -o scripts/vendor/mermaid.min.js
```

Local-first load order:
1. `scripts/vendor/mermaid.min.js`
2. CDN fallback (`https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js`)
