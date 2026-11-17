# Security

NOVA lets a language model propose desktop actions, so the validation layer in `src/nova/actions/validate.py` is the security boundary: the model can only propose, and NOVA decides. See the Security section of the README and `docs/adversarial-results.md`.

## Reporting a problem

Please report vulnerabilities privately through GitHub's **Report a vulnerability** button on the repository's Security tab, not in a public issue. Useful reports include a prompt or input that gets an action past validation, such as an app outside the allowlist, a non-web URL, a path outside the approved folder, or a side effect without confirmation.

This is a personal project maintained in spare time; reports are answered on a best-effort basis.
