# Security policy

If you believe you found a vulnerability in Ushka, please report it privately. Do not open a public issue.

## Reporting a vulnerability

Write to [kleber.code@gmail.com](mailto:kleber.code@gmail.com) with:

- a description of the vulnerability and its impact;
- the steps to reproduce it, ideally a minimal app;
- the Ushka version affected;
- a suggested fix, if you have one.

We acknowledge a report within **2 business days** and send an initial assessment, then keep you
informed until it is fixed. You are credited in the release notes if you wish.

## Responsible disclosure

Please:

- keep the vulnerability private until a fix is released;
- avoid accessing or changing data that is not yours;
- avoid denial-of-service testing against systems you do not own.

## Verifying a release

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

