# AGENT GUIDELINES FOR AUTOPI-EXT

This document outlines the conventions and commands for agentic coding agents working on the `autopi-ext` project.

## 1. Build/Lint/Test Commands

*   **No explicit build process:** This is a Python project and typically doesn't require a separate build step.
*   **Linting:** Use `flake8` or `pylint` for linting.
    *   To lint all files: `flake8 .` or `pylint **/*.py`
    *   To lint a single file: `flake8 <file_path>` or `pylint <file_path>`
*   **Testing:** There are no dedicated test files. For testing `j1939Parser.py`, you can run its `if __name__ == "__main__":` block directly.
    *   To run `j1939Parser.py` examples: `python j1939Parser.py`

## 2. Code Style Guidelines

*   **Imports:**
    *   Organize imports alphabetically.
    *   Separate standard library imports, third-party imports, and local imports with blank lines.
*   **Formatting:** Adhere to PEP 8 guidelines. Use `black` for auto-formatting.
    *   To format all files: `black .`
    *   To format a single file: `black <file_path>`
*   **Types:** Use type hints for function arguments and return values where appropriate.
*   **Naming Conventions:**
    *   Variables and functions: `snake_case`
    *   Classes: `CamelCase`
    *   Constants: `UPPER_SNAKE_CASE`
*   **Error Handling:** Use `try-except` blocks for robust error handling, especially for file operations and external communication.
*   **Comments:** Add comments for complex logic or non-obvious code sections. Docstrings should be used for modules, classes, and functions.
