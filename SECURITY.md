# Security Policy

## Supported versions

Greenwash is pre-1.0. Security fixes are made on the `main` branch and included in the next
release.

## Reporting a vulnerability

Please **do not** open a public issue, discussion, or pull request for security problems.

Report vulnerabilities privately through GitHub:

1. Go to the repository's **Security** tab.
2. Click **Report a vulnerability**.
3. Describe the issue, how to reproduce it, and the impact you expect.

You should receive an acknowledgement within 5 business days. We'll keep you updated while we
investigate and will credit you in the release notes unless you prefer to stay anonymous.

## What's in scope

Examples of issues we want to hear about:

- Bypassing webhook signature verification.
- A pull request changing Greenwash's behavior for its own analysis (for example, disabling checks
  through the pull request itself).
- Leaking credentials — the GitHub App private key, webhook secret, or TypeSafe API key — through
  logs, responses, or reports.
- Sending data to TypeSafe or GitHub beyond what [docs/privacy.md](docs/privacy.md) describes.

## Operating Greenwash securely

If you self-host Greenwash:

- Keep `GITHUB_PRIVATE_KEY`, `GITHUB_WEBHOOK_SECRET`, and `TYPESAFE_API_KEY` in your host's secret
  store. Never commit them.
- Give the GitHub App only the permissions listed in [docs/self-hosting.md](docs/self-hosting.md).
- Keep the app installable **only on your account** unless you intend to serve other accounts —
  every installation spends your TypeSafe usage.
- Rotate the webhook secret and private key if they may have been exposed.
