const COOKIE_URLS = ["https://x.com", "https://twitter.com"];
const COOKIE_DOMAINS = new Set(["x.com", ".x.com", "twitter.com", ".twitter.com"]);

const fields = {
  count: document.getElementById("count"),
  authToken: document.getElementById("auth-token"),
  ct0: document.getElementById("ct0"),
  twid: document.getElementById("twid"),
  loggedIn: document.getElementById("logged-in"),
  status: document.getElementById("status"),
  exportButton: document.getElementById("export"),
};

document.addEventListener("DOMContentLoaded", refreshSummary);
fields.exportButton.addEventListener("click", exportCookies);

async function readCookies() {
  const all = [];
  for (const url of COOKIE_URLS) {
    const found = await chrome.cookies.getAll({ url });
    all.push(...found);
  }
  return dedupe(all).filter((cookie) => COOKIE_DOMAINS.has(cookie.domain));
}

async function refreshSummary() {
  try {
    const cookies = await readCookies();
    const names = new Set(cookies.map((cookie) => cookie.name));
    fields.count.textContent = String(cookies.length);
    fields.authToken.textContent = yesNo(names.has("auth_token"));
    fields.ct0.textContent = yesNo(names.has("ct0"));
    fields.twid.textContent = yesNo(names.has("twid"));
    fields.loggedIn.textContent = yesNo(names.has("auth_token") && names.has("ct0"));
  } catch (error) {
    fields.status.textContent = error.message;
  }
}

async function exportCookies() {
  fields.exportButton.disabled = true;
  fields.status.textContent = "Preparing export...";
  try {
    const cookies = await readCookies();
    const payload = cookies.map(toPlaywrightCookie);
    const blob = new Blob([JSON.stringify(payload, null, 2) + "\n"], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    await chrome.downloads.download({
      url,
      filename: "xoctopus-x-cookies.json",
      saveAs: true,
    });
    fields.status.textContent = `Exported ${payload.length} cookies.`;
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  } catch (error) {
    fields.status.textContent = error.message;
  } finally {
    fields.exportButton.disabled = false;
  }
}

function toPlaywrightCookie(cookie) {
  return {
    name: cookie.name,
    value: cookie.value,
    domain: cookie.domain,
    path: cookie.path || "/",
    expires: cookie.expirationDate ? Math.trunc(cookie.expirationDate) : -1,
    httpOnly: Boolean(cookie.httpOnly),
    secure: Boolean(cookie.secure),
    sameSite: normalizeSameSite(cookie.sameSite),
  };
}

function normalizeSameSite(value) {
  if (value === "no_restriction") {
    return "None";
  }
  if (value === "strict") {
    return "Strict";
  }
  return "Lax";
}

function dedupe(cookies) {
  const seen = new Map();
  for (const cookie of cookies) {
    seen.set(`${cookie.domain}\t${cookie.path}\t${cookie.name}`, cookie);
  }
  return Array.from(seen.values());
}

function yesNo(value) {
  return value ? "yes" : "no";
}
