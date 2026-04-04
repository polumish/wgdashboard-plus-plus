# Security Policy

## Supported versions

Only the **latest minor release** receives security updates.

| Version | Supported |
|---------|-----------|
| 1.0.x   | ✅        |
| < 1.0   | ❌        |

## Reporting a vulnerability

**Do not report security issues via public GitHub issues.**

Instead, email **polumish@gmail.com** with:
- Description of the issue
- Steps to reproduce
- Impact assessment
- Suggested fix (if any)

I'll respond within **7 days** and work with you on a fix and disclosure timeline.

## Scope

This project is a fork of [WGDashboard](https://github.com/donaldzou/WGDashboard). Security issues in the **upstream code** (not fork-specific additions) should also be reported to the [upstream project](https://github.com/donaldzou/WGDashboard/security).

## Best practices for users

- **Change the default `admin`/`admin` credentials immediately** after first login
- **Use HTTPS** via reverse proxy when exposing the dashboard publicly
- **Enable TOTP** for admin accounts
- **Use Trusted IPs** to restrict TOTP bypass to known networks only
- **Keep your installation updated** — check releases regularly
- **Review logs** for suspicious activity in `/opt/WGDashboard/src/log/`
