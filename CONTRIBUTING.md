# Contributing to Kokoro TTS

Thank you for your interest in contributing to Kokoro TTS! This document provides guidelines and instructions for contributing to this text-to-speech tool.

## Development Setup

1. Fork the repository
2. Clone your fork: `git clone https://github.com/gondaliyashreyan1/kokoro-tts.git`
3. Navigate to the project directory: `cd kokoro-tts`
4. Create a virtual environment: `python -m venv .venv`
5. Activate the virtual environment:
   - On Windows: `.venv\Scripts\activate`
   - On macOS/Linux: `source .venv/bin/activate`
6. Install the dependencies: `pip install -r requirements.txt` or `uv sync`
7. Download required model files as mentioned in the README.md

## Code Structure

- `kokoro-tts` - Main Python script with CLI functionality
- `requirements.txt` - Project dependencies
- `pyproject.toml` - Project configuration
- Model files:
  - `kokoro-v1.0.onnx` - The TTS model
  - `voices-v1.0.bin` - Voice data for the model

## Code Style Guidelines

- Follow PEP 8 style guide for Python code
- Use descriptive variable and function names
- Add docstrings to functions and classes
- Maintain consistent indentation (4 spaces)
- Document new features or changes in the README.md
- Group imports as follows:
  - Standard library imports
  - Third-party imports
  - Local application imports

## Pull Request Guidelines

Before submitting a pull request, please make sure that:

- Your code follows the project's coding style
- You have tested your changes thoroughly
- The commit messages are clear and descriptive and follow the conventions specified in [COMMIT_GUIDELINES.md](COMMIT_GUIDELINES.md)
- You have documented your changes in the README.md if necessary
- Your changes don't break existing functionality
- You've added proper error handling where needed

When opening a pull request, please use the provided pull request template. It helps ensure all necessary information is included.

## Submitting Changes

1. Create a new branch: `git checkout -b feature/your-feature-name`
2. Make your changes
3. Test thoroughly
4. Commit with clear messages following the guidelines in [COMMIT_GUIDELINES.md](COMMIT_GUIDELINES.md)
5. Push to your fork: `git push origin feature/your-feature-name`
6. Open a Pull Request against the main repository

## Issue Reporting and Questions

For bug reports and feature requests, please use the provided issue templates:
- **Bug Report**: For reporting bugs or unexpected behavior
- **Feature Request**: For suggesting new features or improvements

For questions and discussions about the project, please use GitHub Discussions instead of opening an issue. This helps keep the issue tracker focused on bugs and features.

When reporting issues, please:
- Use a clear and descriptive title
- Provide all the information requested in the issue template
- Include steps to reproduce the problem (for bugs)
- Specify your environment (OS, Python version, etc.)
- Include any relevant error messages or logs
- Check existing issues to avoid duplicates

## Feature Requests

Feature requests are welcome. To submit a feature request:

- Use a clear and descriptive title
- Provide a detailed description of the proposed feature
- Explain why this feature would be useful to Kokoro TTS users
- If possible, suggest how it might be implemented

## Testing

Before submitting your changes, make sure to test:

- Basic functionality with text files
- EPUB processing if your changes affect it
- PDF processing if your changes affect it
- Voice blending if your changes affect it
- Audio output quality and format options

## License

By contributing to this project, you agree that your contributions will be licensed under the same [MIT License](LICENSE) as the project. 
