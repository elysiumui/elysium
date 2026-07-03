# Contributing

How to file a bug, propose a feature, and send a PR. The
authoritative source is
[`CONTRIBUTING.md`](https://github.com/elysiumui/elysium/blob/main/CONTRIBUTING.md)
at the repo root; this page mirrors the essentials.

## Bugs

File at [GitHub Issues](https://github.com/elysiumui/elysium/issues).
Include:

- The exact `elysium --version` output.
- Your OS + Python version (`elysium doctor` prints both).
- A minimum reproducer (one Python file + one `.esk` folder).
- Whether the bug appears with the `stub` AI provider (rules out
  network issues).

## Feature proposals

For small additions, file an issue describing the use case. For
larger changes (new component, new subpackage, new public API),
open a discussion first. The maintainers respond within a week.

## Pull requests

1. Fork + branch.
2. `pip install -e ".[dev]"` and `cd elysium-native && cargo build`
   to build from source.
3. Make changes.
4. Run `pytest python/elysium/` and `cargo test --manifest-path
   elysium-native/Cargo.toml`.
5. `ruff check .` and `pyright python/elysium/`.
6. Add a changelog entry under "Unreleased".
7. Open the PR.

A reviewer responds within a week. Expect feedback on:

- Public API design.
- Test coverage.
- Docs (a feature without docs is not done).

## Docs PRs

The docs live at `docs/` (Framework) and `docs-designer/` (Designer).
Build locally with:

```sh
mkdocs serve -f mkdocs.yml          # framework
mkdocs serve -f mkdocs-designer.yml # designer
```

Both build clean under `--strict`. No em-dashes, American English
spelling.

## Style

- Python: ruff + pyright for linting / typing.
- Rust: `cargo fmt` + `cargo clippy`.
- Docs: see [the docs style guide](https://github.com/elysiumui/elysium/blob/main/docs/STYLE.md).
- Commit messages: imperative present tense; reference issue
  numbers when relevant.

## Coordinated disclosure

For security issues do **not** open a public issue. Email
`security@elysiumui.com` with details. We acknowledge within 24
hours and ship a fix within 14 days for verified vulnerabilities.

## License

By contributing, you agree your changes ship under the project's
permissive license. No CLA required.

## Community

- GitHub Discussions for proposals and questions.
- Discord (link in the repo README) for real-time chat.
- The Designer's marketplace for sharing skins (no review required
  beyond the registry's signature check).

## See also

- [Roadmap](roadmap.md)
- [FAQ](faq.md)
