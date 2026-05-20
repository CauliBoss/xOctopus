# xOctopus Cookie Exporter

This Chrome/Chromium extension exports only X/Twitter cookies in Playwright JSON
format for xOctopus terminal-only deployments.

## Install Locally

1. Open `chrome://extensions`.
2. Enable Developer mode.
3. Click Load unpacked.
4. Select `browser-extension/xoctopus-cookie-exporter`.

## Export Cookies

1. Open `https://x.com` in the same browser and log in manually.
2. Click the xOctopus Cookie Exporter extension.
3. Confirm `auth_token` and `ct0` show `yes`.
4. Click Export.
5. Move `xoctopus-x-cookies.json` to the server as `data/cookies/x.cookies.json`.

Then configure xOctopus:

```toml
[auth]
mode = "cookies"
cookies_file = "data/cookies/x.cookies.json"
cookies_format = "playwright"
refresh_cookies = true
```

Validate on the server:

```bash
xoctopus auth status
xoctopus auth validate
```

The exported file can access your X session. Store it like a password and do not
commit it to Git.
