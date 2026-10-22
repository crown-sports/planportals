# Releases and downloads

PlanPortals is distributed through [GitHub Releases](https://github.com/crown-sports/planportals/releases). Initial 0.x releases are experimental pre-releases. It is not published on PyPI.

| Asset | Contents |
| --- | --- |
| `planportals-source.zip` | Explicitly audited source, docs, tests, CI and the explicitly listed generated figures |
| `planportals-VERSION.tar.gz` | Python source distribution |
| `planportals-VERSION-py3-none-any.whl` | Installable package and metadata; no figure, dataset or model |
| `SHA256SUMS` | SHA256 checksums for those three assets |

GitHub also provides source archives of the public tag. All downloads exclude real drawings, annotations, datasets, weights, private results, credentials and the original application's Git history. MIT covers repository code; external inputs and dependencies retain their licenses.

## Maintainer checks

Use a clean standalone checkout. Update version, changelog, citation and validation notes before a tag.

```bash
python -m pip install -e '.[dev]'
ruff check .
ruff format --check .
pytest
python tools/render_demo.py --check
python tools/release.py --check
python -m build
python tools/release.py --output dist/planportals-source.zip
```

Review all source and archive members. Keep the public history independent of any private application. The allowed images are `examples/demo.png` and `examples/workflow.png`; the former is an actual result rendered on code-generated geometry; do not add real images or per-case result files. Confirm the renderer's documented check scope, not just a visually attractive picture.

Push the reviewed source, verify the exact commit in Python 3.10 and 3.12 CI, then tag it. Prepare a draft release, upload the three artifacts and checksums, verify uploaded digests and publish the experimental release. Test the wheel in a fresh environment before publication.

Verify downloads with `sha256sum -c SHA256SUMS` on Linux, or `shasum -a 256 -c SHA256SUMS` on macOS. Install the wheel locally with pip. No automated dataset or model upload is configured.

## v0.2.0 compatibility

This release adds commands without changing the existing input/export schemas.
Install the pinned tag with `python -m pip install "git+https://github.com/crown-sports/planportals.git@v0.2.0"`,
or use the matching release wheel. This is a GitHub experimental pre-release;
no PyPI upload or pretrained-model download is configured.

Build artifacts from a clean export of the exact reviewed release commit into a
new output directory. Do not reuse a previous release's `dist/` files. Verify
package metadata and imported `__version__` from the wheel in a fresh environment,
then record SHA-256 checksums only for that version's wheel, sdist and audited
source ZIP. Existing tags and assets retain their original contents.

The additional `examples/workflow.png` is an original, data-driven figure from the shared generated walkthrough. Only the names in `PUBLIC_IMAGES` are allowed; all RGB, size and metadata checks still apply.
