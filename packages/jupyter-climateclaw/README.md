# jupyter_climateclaw

`jupyter_climateclaw` is a Jupyter AI module, a package
that registers additional model providers and slash commands for the Jupyter AI
extension.

## Requirements

- Python 3.8 - 3.12
- JupyterLab 4

## Install

To install the extension, execute:

```bash
pip install jupyter_climateclaw

## Uninstall

To remove the extension, execute:

```bash
pip uninstall jupyter_climateclaw
```

## Contributing

### Development install

```bash
cd jupyter-climateclaw
pip install -e "."
```

### Development uninstall

```bash
pip uninstall jupyter_climateclaw
```

#### Backend tests

This package uses [Pytest](https://docs.pytest.org/) for Python testing.

Install test dependencies (needed only once):

```sh
cd jupyter-climateclaw
pip install -e ".[test]"
```

To execute them, run:

```sh
pytest -vv -r ap --cov jupyter_climateclaw
```
