# Development Guide

This section codifies expectations for contributors who touch documentation, docstrings, or logic.

## Docstrings and inline documentation

- All helper functions and classes follow **Google Python Style Guide** docstrings. Each docstring should explain the purpose, outline ``Args``, ``Returns`` (when applicable), and ``Raises`` for notable exceptions.
- Module-level docstrings should provide context for the helpers exported by that module.
- Keep docstrings close to the code so tooling (like ``pydoc`` or IDE hovers) surfaces accurate information.
- When introducing new features, update the relevant `.md` file in ``docs/`` and add or adjust docstrings describing the new behavior.

## Project layout reminders

- `ultravision/cli.py`: entrypoint for the CLI; connect to images/api/util writers.
- `ultravision/api.py`: OpenAI-compatible chat completion calls and response extraction.
- `ultravision/images.py`: disk helpers, resizing, metadata, and message builders.
- `ultravision/writer.py`: format-specific record serialization.
- `ultravision/util.py`: concurrency and backoff utilities.
- `ultravision/web/server.py`: FastAPI server for the browser UI.

## Testing and validation

Run the existing test suite before merging:

```bash
pip install -e '.[dev]'
pytest
```

The tests focus on image helpers, writers, resume behavior, and concurrency logic. Keep tests in sync when changing functionality, especially around deduplication or resume.

## Packaging and release

- `pyproject.toml` defines metadata used when publishing wheels or source distributions.
- Use `pip install .` or `pip install -e .` during development to ensure all dependencies are resolved.
- README and docs should clearly describe CLI usage, web companion instructions, and configuration knobs.

## Recommended next steps when updating docs

1. Add or update structured documentation in `docs/` to reflect new behaviors and UX.
2. Ensure docstrings exist for any exported helper so IDEs and contributors understand how to use it.
3. Run tests locally and mention the command in PR descriptions.
