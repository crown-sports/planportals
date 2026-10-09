# Contributing to PlanPortals

Small fixes can be proposed as pull requests. Discuss larger changes with an input example, expected behavior and evaluation plan. Follow [community conduct](CODE_OF_CONDUCT.md); use [private reporting](SECURITY.md) for vulnerabilities.

```bash
python -m pip install -e '.[dev]'
ruff check .
ruff format --check .
pytest
python tools/render_demo.py --check
python tools/release.py --check
python -m build
```

Keep domain objects independent of I/O and replace observations through explicit adapters. Preserve original pixel coordinates, unit semantics, rejection reasons and versioned outputs. No import-time network calls, hidden downloads or model initialization. Tests should expose failures such as duplicate evidence, ambiguous geometry and unsafe inference from missing information.

Only one reviewed composite image generated from source code is allowed in the public tree. Create fixtures in tests. Keep real drawings, annotation files, datasets, weights and per-case results outside the checkout. Explain the scope of aggregate measurements; generated observations do not establish real-image detection accuracy. Retain attribution to established methods and dependencies.

By contributing, you confirm that you can license the submitted code under MIT and have retained required notices. See [release checks](docs/releasing.md).
