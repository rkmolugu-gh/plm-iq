# Contributing to PLM-IQ

Thank you for your interest in contributing to PLM-IQ! This guide will help you get started.

## 🌟 Ways to Contribute

- 🐛 **Report Bugs**: Help us identify and fix issues
- 💡 **Suggest Features**: Share ideas for new functionality
- 📖 **Improve Documentation**: Help make our docs clearer
- 🧑‍💻 **Submit Code**: Fix bugs, add features, or improve performance
- 🧪 **Write Tests**: Help us maintain quality
- 🎨 **Design & UX**: Improve user interfaces and experiences

---

## 🚀 Getting Started

### 1. Fork the Repository

Click the "Fork" button on the [PLM-IQ GitHub page](https://github.com/rkmolugu/plm-iq).

### 2. Clone Your Fork

```bash
git clone https://github.com/YOUR_USERNAME/plm-iq.git
cd plm-iq
```

### 3. Create a Branch

```bash
git checkout -b feature/your-feature-name
# or
git checkout -b fix/your-bug-fix
```

### 4. Set Up Development Environment

```bash
# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# Install dependencies
pip install -e ".[dev]"

# Install pre-commit hooks
pre-commit install
```

---

## 📋 Development Guidelines

### Code Style

We use **Ruff** for linting and formatting:

```bash
# Check code style
ruff check .

# Format code
ruff format .

# Auto-fix issues
ruff check --fix .
```

### Type Hints

Please add type hints to all new functions:

```python
def process_document(file_path: str, options: dict) -> Document:
    """Process a document and return structured data."""
    ...
```

### Testing

Write tests for new functionality:

```bash
# Run all tests
pytest

# Run tests with coverage
pytest --cov

# Run specific test file
pytest tests/test_document_processor.py
```

### Documentation

- Update docstrings for modified functions
- Update relevant documentation in `docs/`
- Add examples for new features

---

## 🐛 Reporting Bugs

### Before Submitting an Issue

1. Check if the bug has already been reported in [Existing Issues](https://github.com/rkmolugu/plm-iq/issues)
2. Update to the latest version to see if the bug persists

### Bug Report Template

```markdown
**Description**
A clear description of the bug.

**Steps to Reproduce**
1. Step 1
2. Step 2
3. Step 3

**Expected Behavior**
What you expected to happen.

**Actual Behavior**
What actually happened.

**Environment**
- OS: [e.g., Windows 11, Ubuntu 22.04]
- Python Version: [e.g., 3.11.5]
- PLM-IQ Version: [e.g., 0.1.0]

**Additional Context**
Screenshots, logs, or other relevant information.
```

---

## 💡 Suggesting Features

We love new ideas! When suggesting a feature:

1. Check if it's already suggested in [Discussions](https://github.com/rkmolugu/plm-iq/discussions)
2. Explain the use case and why it would be valuable
3. Consider starting with a discussion before creating an issue

### Feature Request Template

```markdown
**Feature Description**
A clear description of the proposed feature.

**Use Case**
Why is this feature needed? What problem does it solve?

**Proposed Solution**
How should this feature work?

**Alternatives Considered**
Are there alternative approaches?

**Additional Context**
Screenshots, mockups, or examples.
```

---

## 📝 Pull Request Process

### Before Submitting

1. Ensure all tests pass: `pytest`
2. Ensure code style passes: `ruff check . && ruff format --check .`
3. Update documentation if needed
4. Add tests for new functionality

### PR Title Format

```
<type>(<scope>): <description>

Examples:
feat(api): add document versioning endpoint
fix(search): resolve elasticsearch connection issue
docs(readme): update installation instructions
```

### Types

- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `style`: Code style changes (formatting, etc.)
- `refactor`: Code refactoring
- `test`: Adding or updating tests
- `chore`: Maintenance tasks

### PR Description Template

```markdown
## Description
Brief description of changes.

## Type of Change
- [ ] Bug fix
- [ ] New feature
- [ ] Breaking change
- [ ] Documentation update

## Testing
Describe how you tested your changes.

## Checklist
- [ ] Tests added/updated
- [ ] Documentation updated
- [ ] Code style checks pass
- [ ] All tests pass
```

---

## 🧑‍⚖️ Code of Conduct

Please read our **[Code of Conduct](CODE_OF_CONDUCT.md)** before participating.

---

## 💬 Getting Help

- 💬 **Discussions**: [GitHub Discussions](https://github.com/rkmolugu/plm-iq/discussions)
- 🐛 **Issues**: [GitHub Issues](https://github.com/rkmolugu/plm-iq/issues)
- 📧 **Email**: plm-iq@users.noreply.github.com

---

## 🎉 Recognition

Contributors are recognized in:
- Release notes
- README contributors section
- Annual contributor highlights

Thank you for contributing to PLM-IQ! 🚀
