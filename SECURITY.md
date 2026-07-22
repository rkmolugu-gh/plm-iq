# Security Policy

## 🔒 Reporting Security Vulnerabilities

We take the security of PLM-IQ seriously. If you discover a security vulnerability, we appreciate your help in disclosing it to us in a responsible manner.

---

## 📞 How to Report

**Please DO NOT report security vulnerabilities through public GitHub issues.**

Instead, please report them via email to:

📧 **plm-iq-security@users.noreply.github.com**

Or use GitHub's **[Security Advisories](https://github.com/rkmolugu/plm-iq/security/advisories)** feature.

---

## 📋 What to Include

When reporting a security vulnerability, please include:

1. **Description**: A clear description of the vulnerability
2. **Steps to Reproduce**: Detailed steps to reproduce the issue
3. **Impact**: Potential impact of the vulnerability
4. **Suggested Fix**: If you have ideas for fixing it
5. **Your Contact**: How we can reach you for follow-up questions

Example:
```
Vulnerability: SQL Injection in search endpoint
Location: /api/v1/search
Impact: High - Could allow unauthorized data access
Steps:
  1. Send POST request to /api/v1/search with...
  2. Observe...
Suggested Fix: Use parameterized queries
Contact: your-email@example.com
```

---

## ⏱️ Response Timeline

We aim to:

- **Acknowledge** receipt within **48 hours**
- **Provide initial assessment** within **5 business days**
- **Release a fix** as soon as possible, depending on complexity

---

## 🛡️ Supported Versions

We provide security updates for the following versions:

| Version | Supported |
|---------|-----------|
| 0.1.x (Latest) | ✅ Yes |
| < 0.1.0 | ❌ No |

---

## 🔐 Security Best Practices

### For Users

1. **Keep Dependencies Updated**
   ```bash
   pip audit
   pip install --upgrade package-name
   ```

2. **Use Environment Variables**
   - Never commit `.env` files
   - Use strong, unique secrets for `SECRET_KEY`

3. **Enable Authentication**
   - Configure proper user authentication
   - Use HTTPS in production
   - Implement rate limiting

4. **Regular Backups**
   - Backup your database regularly
   - Test restoration procedures

### For Developers

1. **Input Validation**
   - Validate all user inputs
   - Use Pydantic models for request validation

2. **SQL Injection Prevention**
   - Use SQLAlchemy ORM (parameterized queries)
   - Never use string formatting for SQL

3. **XSS Prevention**
   - Sanitize user-generated content
   - Use Jinja2's auto-escaping

4. **Authentication & Authorization**
   - Hash passwords with bcrypt
   - Use JWT tokens securely
   - Implement proper role-based access control

5. **Dependencies**
   - Regularly update dependencies
   - Monitor for vulnerable packages
   - Use `pip-audit` or `safety` tools

---

## 🚨 Known Security Issues

Check our **[GitHub Security Advisories](https://github.com/rkmolugu/plm-iq/security/advisories)** for any disclosed vulnerabilities and their fixes.

---

## 🏆 Hall of Fame

We thank the following security researchers for responsibly disclosing vulnerabilities:

<!-- Add names here with their permission -->
<!-- | Researcher | Vulnerability | Date | -->
<!-- |------------|---------------|------| -->

---

## 📚 Additional Resources

- **[OWASP Top 10](https://owasp.org/www-project-top-ten/)**
- **[Python Security](https://python-security.readthedocs.io/)**
- **[FastAPI Security](https://fastapi.tiangolo.com/tutorial/security/)**

---

## ⚖️ Disclosure Policy

We follow **coordinated vulnerability disclosure**:

1. **Report Received** → We acknowledge within 48 hours
2. **Investigation** → We verify and assess the vulnerability
3. **Fix Development** → We develop and test a fix
4. **Coordinated Release** → We release the fix and notify the reporter
5. **Public Disclosure** → After fix is available, we may publish details

We request that you:
- Give us reasonable time to fix the issue before public disclosure
- Not access or modify data that doesn't belong to you
- Not perform actions that could negatively affect other users

---

## 📞 Contact

For security-related questions or concerns:

📧 **Email**: plm-iq-security@users.noreply.github.com

For non-security bugs, please use **[GitHub Issues](https://github.com/rkmolugu/plm-iq/issues)**.

---

<div align="center">
  <strong>🛡️ Security is everyone's responsibility. Thank you for helping keep PLM-IQ safe! 🛡️</strong>
</div>
