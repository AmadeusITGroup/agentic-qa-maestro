# Security Policy

## Supported Versions
| Version | Supported          |
| ------- | ------------------ |
| latest  | :white_check_mark: |

## Reporting a Vulnerability
If you discover a security vulnerability, please report it responsibly.

- **Do not open a public GitHub issue for security vulnerabilities.**
- Email creation-platform@amadeus.com with:
  - Description of the vulnerability
  - Steps to reproduce
  - Relevant logs or screenshots
  - Suggested severity

We will acknowledge receipt within 3 business days and aim to provide a fix or mitigation plan within 30 days, depending on severity.

## Security Best Practices
- Never commit secrets. Use environment variables or `.env` files (excluded from version control).
- Use `${env:VAR_NAME}` substitution in configuration files instead of hardcoding credentials.
- Rotate credentials regularly.
- Enable TLS verification for all production connections.
- Restrict agent permissions to the minimum required scope.
