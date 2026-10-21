# iphone-lab

Free iPhone-simulator probe on GitHub Actions macOS runners (free for public repos) for testing Apple Shortcuts.

- `shortcuts/` sanitized Shortcut plists (ntfy topic and email replaced with placeholders; no personal data)
- `sandbox/` Linux structural validator built from Apple's iOS 27 action definitions (`sbx.py validate|run|dump`)
- `src/` build scripts (shortcutkit / Cherri); set `NTFY_TOPIC` env var locally, never commit it
- `.github/workflows/ios.yml` boots an iPhone simulator, screenshots it, probes for the Shortcuts app and the `shortcuts` CLI, lints and validates the plists.

This repo and its Action logs are public. Do not commit secrets.
