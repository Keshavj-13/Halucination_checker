# Contributing

Thanks for contributing to Halucination_checker.

## Getting Started

1. Fork and clone the repository.
2. Create a feature branch for your changes.
3. Set up the backend and frontend environments.
4. Make focused changes with tests/docs where applicable.

## Development Workflow

- Keep pull requests small and scoped.
- Follow existing project style and structure.
- Update relevant documentation when behavior changes.
- Ensure local checks pass before opening a PR.

## Local Validation

### Backend

```bash
cd backend
python -m pip install -r requirements.txt
python -m pytest -q
```

### Frontend

```bash
cd frontend
npm install
npm run build
```

## Pull Request Checklist

- [ ] I tested the changes locally
- [ ] I updated documentation when needed
- [ ] I kept the change scoped to the stated goal
- [ ] I confirmed no secrets or sensitive data were added

## Licensing

By contributing, you agree that your contributions are licensed under the GNU General Public License v3.0 (or later) used by this repository.
