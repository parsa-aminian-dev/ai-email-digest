# Gmail OAuth setup

The adapter only calls `users.messages.list` and `users.messages.get`. It never marks messages read, moves/deletes messages, or sends mail through Gmail. Authorize only `https://www.googleapis.com/auth/gmail.readonly`.

1. Create a personal Google Cloud project and enable the Gmail API.
2. Configure the OAuth consent screen. For testing, add your own Gmail address as a test user.
3. Create an OAuth web client for a one-time authorization with Google's OAuth Playground, and add `https://developers.google.com/oauthplayground` as an authorized redirect URI.
4. Open [OAuth Playground](https://developers.google.com/oauthplayground). In its settings, enable **Use your own OAuth credentials** and enter your client ID and secret.
5. Enter the read-only scope above, authorize your own account, then exchange the authorization code for tokens. Copy the refresh token into your private `.env`. Do not commit screenshots, token files, or the token itself.
6. Set `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, and `GOOGLE_REFRESH_TOKEN`. The backend obtains short-lived access tokens in memory using the refresh-token grant. It writes neither access nor refresh tokens to SQLite.
7. Disable demo mode and run `python -m src.digest.cli ingest`. Review the counts; logs contain no email text or token values.

[Google documents](https://developers.google.com/identity/protocols/oauth2#expiration) a seven-day refresh-token lifetime for an external consent screen in Testing when Gmail scopes are requested. Reauthorize when needed or configure the consent screen's production publishing status for personal use; verification and account restrictions depend on Google's policies. Never solve authorization errors by adding write or send scopes.

Digest delivery uses independent SMTP credentials. With Gmail SMTP, use an account/app-password arrangement permitted by your account configuration; do not reuse your OAuth client as a delivery credential.

References: [read-only scope](https://developers.google.com/workspace/gmail/api/auth/scopes), [list](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages/list), [get](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages/get), [OAuth offline access](https://developers.google.com/identity/protocols/oauth2/web-server#offline).
