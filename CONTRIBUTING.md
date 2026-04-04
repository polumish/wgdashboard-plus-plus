# Contributing to WgDashboard++

Thanks for your interest! This is a small fork, and any help is appreciated.

## Types of contributions welcome

- 🐛 **Bug reports** — use the issue template
- 💡 **Feature suggestions** — especially for UX improvements
- 🧪 **OPNsense integration testing** — the feature is Alpha and needs real-world feedback
- 📖 **Documentation fixes** — typos, clarifications, translations
- 🔌 **Pull requests** for bug fixes and small features

## Development setup

```bash
git clone https://github.com/polumish/wgdashboard-plus-plus.git
cd wgdashboard-plus-plus/src
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install pytest gunicorn
./wgd.sh start
```

### Frontend dev

```bash
cd src/static/app
npm install
npm run dev  # hot-reload dev server
# Or build for production:
npm run build
```

### Running tests

```bash
cd src
python -m pytest tests/ -v
```

## Pull request guidelines

1. **Keep PRs focused** — one feature or fix per PR
2. **Test locally** — make sure `pytest` passes
3. **Build frontend** if you changed Vue files — commit the `src/static/dist/` output
4. **Rebuild before commit** — our CI expects updated dist files
5. **Describe the why** — what problem does this solve?

## Versioning

We use **X.YZ** scheme:
- **X** — major (global behavior change)
- **Y** — feature release (+0.1)
- **Z** — bugfix (+0.01)

Examples: `v1.0` → `v1.01` (bugfix) → `v1.1` (feature) → `v2.0` (major)

## Code style

- **Python:** follow existing patterns, no strict linting enforced yet
- **Vue/JS:** existing codebase uses Options API with some Composition API — match the file you're editing
- **CSS:** prefer Bootstrap utilities over custom CSS; if custom CSS needed, add to `src/static/app/src/css/dashboard.css`

## Relationship to upstream

This fork tracks [donaldzou/WGDashboard](https://github.com/donaldzou/WGDashboard). For bugs in the **original** dashboard code (not our additions), prefer reporting upstream first.

## License

By contributing, you agree your contributions will be licensed under Apache 2.0, same as the project.
