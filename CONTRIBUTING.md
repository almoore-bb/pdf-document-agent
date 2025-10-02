# Contributing to PDF Document Agent

Thank you for your interest in contributing to the PDF Document Agent project! This document provides guidelines for contributing.

## Getting Started

1. Fork the repository on GitHub
2. Clone your fork locally
3. Create a new branch for your feature or bug fix
4. Make your changes
5. Test your changes thoroughly
6. Submit a pull request

## Development Setup

### Prerequisites
- AWS CLI configured
- Terraform >= 1.2.0
- Python 3.13
- Docker (for Lambda layer building)

### Local Development
```bash
# Clone your fork
git clone https://github.com/your-username/pdf-document-agent.git
cd pdf-document-agent

# Create a development branch
git checkout -b feature/your-feature-name

# Test your changes
python3 -m pytest tests/ (when tests are added)

# Validate Terraform
cd deployment
terraform validate
```

## Code Style

- Follow PEP 8 for Python code
- Use meaningful variable and function names
- Add docstrings to all functions
- Keep functions focused and small
- Add error handling and logging

## Testing

- Add unit tests for new functions
- Test with both S3 URIs and HTTP URLs
- Verify error handling scenarios
- Test with various PDF types and sizes

## Pull Request Process

1. Update documentation if needed
2. Add tests for new functionality
3. Ensure all tests pass
4. Update the README.md if needed
5. Submit a pull request with:
   - Clear description of changes
   - Link to any related issues
   - Screenshots if UI changes

## Reporting Issues

When reporting issues, please include:
- Clear description of the problem
- Steps to reproduce
- Expected vs actual behavior
- CloudWatch logs if available
- PDF sample (if not sensitive)

## Feature Requests

For new features:
- Check existing issues first
- Describe the use case
- Explain the expected behavior
- Consider implementation complexity

## Code of Conduct

- Be respectful and inclusive
- Focus on constructive feedback
- Help others learn and grow
- Follow the project's technical standards