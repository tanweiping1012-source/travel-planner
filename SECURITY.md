# Security Policy

## Supported Scope

This project is a read-only travel planning Skill. Security reports should focus
on:

- Credential or session leakage
- Browser automation escaping the documented read-only boundary
- Unsafe subprocess or file handling
- Disabled TLS verification
- Provider responses exposing private account data

## Reporting

Do not open a public issue containing credentials, cookies, personal travel
history, or reproduction data tied to a real account. Use a private security
advisory in GitHub or another private channel configured by the repository owner.

## Secrets

- Store the Amap key in macOS Keychain, another operating-system secret
  manager, or an ephemeral `AMAP_API_KEY` environment variable.
- Never commit `.env` files.
- Never paste API keys into issues, screenshots, examples, or chat transcripts.
- Rotate a key immediately after accidental disclosure.
- Keep browser passwords, SMS codes, cookies, and storage state outside the
  project directory.

## Browser Data

The repository must never contain:

- Browser profile directories
- Cookie exports
- Playwright or Chromium storage state
- HAR or network capture files
- Screenshots showing account or price-personalization data
- Raw Xiaohongshu or OTA page dumps

Normalized examples must use synthetic URLs and fictional user data.

## Travel Privacy

Origin, destination, dates, budget, accessibility needs, and travel style can
identify or profile a person when combined. Runtime artifacts belong under an
ignored temporary directory and must not be committed.

## Dependency Boundary

The community 12306 MCP is installed locally at a pinned commit and patched
during setup. Its source and virtual environment are excluded from releases.
Review upstream changes before updating the pinned commit.

## Release Gate

Create releases only through:

```bash
./scripts/prepare_release.sh
```

Then inspect and audit the generated allowlisted directory. Do not publish the
working Skill directory directly.
