# Contributing

Issues and pull requests are welcome, especially from program directors and residents who use the ACP
IM-ITE. Report layouts change from year to year, so a note saying "the 20XX roster has a new column" is useful.

**Ground rules**
1. **Never include real resident or program data** in issues, pull requests, tests or screenshots.
   Describe file layouts with invented values. The pre-commit hook and CI block data files and emails.
2. Keep analysis logic in `ite_core/` as pure functions with pytest tests on synthetic data.
3. Changes to any method must update [docs/METHODS.md](docs/METHODS.md) and [CHANGELOG.md](CHANGELOG.md).
4. Run before opening a PR:
   ```bash
   .venv/bin/python -m pytest
   .venv/bin/ruff check . && .venv/bin/ruff format --check .
   ```

By contributing you agree that your contribution is licensed under the Apache License 2.0
(see [LICENSE](LICENSE), section 5).
