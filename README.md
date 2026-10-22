# iphone-lab

Free iPhone-simulator probe on GitHub Actions macOS runners (free for public repos) for testing Apple Shortcuts.

- `shortcuts/` sanitized Shortcut plists (ntfy topic and email replaced with placeholders; no personal data)
- `sandbox/` Linux structural validator built from Apple's iOS 27 action definitions (`sbx.py validate|run|dump`)
- `src/` build scripts (shortcutkit / Cherri); set `NTFY_TOPIC` env var locally, never commit it
- `.github/workflows/ios.yml` boots an iPhone simulator, screenshots it, probes for the Shortcuts app and the `shortcuts` CLI, lints and validates the plists.

This repo and its Action logs are public. Do not commit secrets.

## mobile-mcp smoke test
`.github/workflows/mobile-mcp.yml` runs [mobile-mcp](https://github.com/mobile-next/mobile-mcp) (pinned in
`lab/mcp/package.json`) against a booted simulator over stdio: lists tools and devices, takes a screenshot,
saves one to a file, then opens Settings and taps **General** by coordinates and checks the General page
opened. Run it with `gh workflow run mobile-mcp.yml` (default runner `macos-26-intel`); results land in the
`mobile-mcp-results` artifact. It uses no secrets and is separate from `tap-test.yml`.
