# Azure SSO + Office 365 Email — Dependencies & Testing Guide

This page lists **everything needed to test Azure AD SSO and Office 365 email**
against a real tenant, plus the Office 365 SMTP/MFA situation explained
(why "just a password" no longer works).

Two separate features, two separate dependency sets:

| Feature | Channel role | Needs |
|---|---|---|
| **Azure AD SSO** login | Authentication only | A Microsoft 365 tenant + an **app registration** |
| **O365 email** | Secondary/reporting only | Either **SMTP + app password**, or the same app registration via **Graph** |

---

## 1. Office 365 SMTP — why password login stopped working

Microsoft 365 has disabled **basic authentication (username + password)** for
SMTP AUTH by default and enforces MFA. The old behaviour — `smtp.office365.com:587`,
mailbox user + plain mailbox password — is rejected. There are **two** working
paths:

### Path A — App password (fastest for testing)

1. Make sure the mailbox can do SMTP AUTH:
   `admin.microsoft.com → Users → Active users → mailbox → Mail → Email apps →
   Authenticated SMTP` = **On**.
2. Create an **app password** (works even with MFA on, because app passwords
   are MFA-aware): `myaccount.microsoft.com → Security info → App passwords`
   (app passwords only appear if your tenant has them enabled).
3. Enter the **16-character app password** in the setup wizard's email
   password field, username = the full mailbox address.

In the wizard this is the `office365` provider; SMTP is
`smtp.office365.com:587` (STARTTLS) automatically.

### Path B — Microsoft Graph OAuth2 (recommended for production)

Leave the email field blank in the wizard and instead fill in the Azure
registration (below). `send_report_email` then uses **client-credentials →
Graph `/sendMail`** (`app/ms_oauth.py`), which needs no mailbox password and
survives MFA by design. Requires app permission `Mail.Send` (application type).

---

## 2. Azure AD SSO + Graph email — full dependency checklist

You need a **Microsoft 365 tenant with admin access** (trial tenants work).
All four values go into `infra/.env` after the wizard (SSO is not part of the
wizard form; email-as-Graph is only used when SMTP is left blank).

| # | What you need | Where to get it | → `.env` / backend setting |
|---|---|---|---|
| 1 | **Azure AD tenant ID** | Microsoft Entra admin center → Properties → "Tenant ID" | `AZURE_TENANT_ID` |
| 2 | **App registration (Application ID / client ID)** | Entra admin center → App registrations → New registration | `AZURE_CLIENT_ID` |
| 3 | **Client secret** | The app registration → Certificates & secrets → New client secret | `AZURE_CLIENT_SECRET` |
| 4 | **Admin group object IDs** (members → CLEANUP_APPROVER) | Entra → Groups → the AD group → "Object ID". Comma-separated if several | `AZURE_ADMIN_GROUP_IDS` |
| 5 | **Redirect URI** for SSO login | App registration → Authentication → Web → Redirect URIs. Must be exactly `https://<portal-ip>/api/auth/sso/callback` | used by `ms_oauth.build_authorize_url` |
| 6 | **`openid profile email`** scopes (SSO) | App registration → API permissions → Microsoft Graph → Delegated `openid`, `profile`, `email` | used by `ms_oauth` |
| 7 | **`Mail.Send`** (application permission) for Graph email | App registration → API permissions → Microsoft Graph → Application `Mail.Send`; **Grant admin consent** | used by `send_graph_email` |
| 8 | **A licensed mailbox** for the app account | The Graph `sendMail` sends as the *signed-in/service account* — needs an M365 mailbox license | — |

### SSO callback URL detail

`app/ms_oauth.py` currently hardcodes `PORTAL_BASE_URL = "https://portal.aaditech.local"`
for the redirect_uri. Before testing against a real tenant you must make this
match your portal URL:

- set `PORTAL_BASE_URL` (or the SSO redirect base) to `https://<your-server-ip>`
- register exactly that redirect URI in the app registration

Until that matches, Azure will reject the callback with `AADSTS50011`.

### Testing sequence

1. Add the four `AZURE_*` values to `infra/.env`.
2. Restart the portal: `docker compose restart portal-backend`.
3. Open `https://<server>/login` → "Sign in with Microsoft 365".
   - Success: you get a portal JWT; if your AD group is in `AZURE_ADMIN_GROUP_IDS`
     you are CLEANUP_APPROVER.
   - `AADSTS50011` → redirect URI mismatch (fix step above).
   - `AADSTS90072`/`7000218` → wrong tenant ID.
   - `AADSTS7000215` → wrong client secret.
4. Email: with SMTP app-password (Path A) → the wizard SMTP channel sends
   reports. With Graph (Path B) → `send_graph_email` returns 202.
5. Verify a report email lands (watch `/var/log/aaditech/*.jsonl` for
   `report_email_*` audit entries either way).

---

## 3. What is and isn't implemented in the portal today

- **Code-complete & offline-tested:** SSO login/callback, group→role mapping,
  Graph `sendMail`, SMTP presets. `tests/test_sso_email.py` (6 tests) and
  `test_setup.py` cover these.
- **Not yet validated live:** token exchange against a real tenant, Graph
  `/sendMail`, and an actual SMTP send through gmail/hotmail/office365/
  hostinger — all blocked on a real tenant / real mailbox (Phase 0 spike).

This guide is the checklist to close that gap.
