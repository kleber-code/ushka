# 🛡️ Ushka's Security Policy: Keeping Things Safe & Sound! 💖

(Or: How We Keep Our Little Framework from Getting into Trouble)

At Ushka, we take security seriously. While we strive to be as cute and minimalist as possible, that doesn't mean we compromise on keeping our little framework safe for everyone who uses it. If you believe you've found a vulnerability, we appreciate your help in disclosing it responsibly.

---

## 🚨 Reporting a Vulnerability: Found a Chink in Our Armor?

If you've discovered a security vulnerability in Ushka, please *do not* open a public issue. We kindly request that you report it to us privately first.

**Here's how to report:**

*   **Email Us:** Send a detailed report to [kleber.code@gmail.com](mailto:kleber.code@gmail.com).
*   **Be Specific:** In your report, please include:
    *   A clear description of the vulnerability.
    *   Steps to reproduce the vulnerability (this is super helpful!).
    *   Any potential impact or exploit scenarios.
    *   The version of Ushka you've identified the vulnerability in.
    *   Any suggested mitigations (if you have them!).

---

## ⏳ Our Response Time (We're Pretty Speedy, Promise!)

We aim to acknowledge your report within **2 business days** and provide an initial assessment. Our team will work diligently to investigate and address the vulnerability as quickly as possible. We appreciate your patience as we fix things up!

---

## 🌟 Responsible Disclosure (Being a Good Citizen)

We kindly ask that you:

*   **Do not disclose the vulnerability publicly** until we have had a reasonable amount of time to address it.
*   **Avoid accessing or modifying data** that doesn't belong to you.
*   **Do not engage in denial-of-service attacks** or other disruptive activities.

---

## ✅ Our Commitment (We've Got Your Back!)

When you report a security issue to us in good faith, we commit to:

*   Responding to your report promptly.
*   Keeping you informed about the progress of the fix.
*   Giving you credit for responsible disclosure (if you wish).

Thank you for helping us keep Ushka safe and sound for everyone! Your vigilance makes our community stronger. 💖

---

## 🔐 Verifying a Release

Every release is built by a GitHub Actions workflow and published to PyPI with
trusted publishing (no stored token). You can check that what you downloaded is
what that workflow built, and see what is inside it.

**Build provenance** (needs the [GitHub CLI](https://cli.github.com)):

```console
$ pip download ushka==X.Y.Z --no-deps -d dl
$ gh attestation verify dl/ushka-X.Y.Z-py3-none-any.whl --repo kleber-code/ushka
```

**SBOM**: `ushka.cdx.json` (CycloneDX) is attached to each GitHub release, and
it is attested too. It lists the runtime dependencies that `pip install ushka`
brings in.

```console
$ gh release download vX.Y.Z --repo kleber-code/ushka --pattern ushka.cdx.json
$ gh attestation verify dl/ushka-X.Y.Z-py3-none-any.whl --repo kleber-code/ushka \
    --predicate-type https://cyclonedx.org/bom
```

**PyPI attestations**: the release page on PyPI shows the PEP 740 attestation
for each file.

**How the pipeline is kept safe**

- Every GitHub Action is pinned to a full commit SHA, and Dependabot proposes updates. A test fails the build if one is not pinned.
- Workflows run with the least permissions: the job that publishes cannot build, and the job that builds cannot publish.
- Dependencies are locked with hashes (`pdm.lock`), and CI refuses a stale lock.
- The release is refused if its tag does not match the package version.
- Untrusted text (tag names, PR titles) never goes inside a script: it goes through `env`.

