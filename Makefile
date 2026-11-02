install:
	uv sync

project:
	uv run python main.py

build:
	uv build

package-install:
	uv tool install dist/*.whl --force

lint:
	uv run ruff check .
