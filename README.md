# Defending the Shield — GitHub Pages Starter

This repo is a simple structure to host your OOTP-exported static site on GitHub Pages.

## How it works
- Put your entire OOTP HTML export into `site/current/` (keep folders as-is).
- The landing page (`index.html`) links straight into `site/current/index.html`.
- `assets/css/main.css` contains a basic banner style you can adjust.
- `.nojekyll` disables Jekyll so all your OOTP folders (like ones starting with `_`) work fine.

## Update flow (no Git CLI needed)
1. In GitHub, open this repo → **Add file** → **Upload files**.
2. Drag your OOTP export *contents* into `site/current/` (overwrite prior files).
3. Commit. Your Pages site updates in ~1 minute.

## GitHub Pages setup
- Repo → **Settings** → **Pages** → **Build and deployment**:  
  - **Source:** Deploy from a branch  
  - **Branch:** `main` / **Folder:** `/ (root)` → Save
- Site URL: `https://YOURNAME.github.io/defending-the-shield-site/`

## Optional
- Use a custom domain later (e.g., `shield.simbaseballvision.com`).

— Generated 2025-08-20
