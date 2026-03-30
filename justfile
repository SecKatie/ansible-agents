set positional-arguments

venv := ".venv"

# Run unit tests
unit *args: (venv-check)
    {{venv}}/bin/pytest --import-mode=importlib ansible_collections/seckatie/agents/tests/unit/ {{args}}

# Run integration tests
integration *args: (venv-check)
    {{venv}}/bin/pytest --import-mode=importlib ansible_collections/seckatie/agents/tests/integration/ {{args}}

# Run all tests
test *args: (venv-check)
    {{venv}}/bin/pytest --import-mode=importlib ansible_collections/seckatie/agents/tests/ {{args}}

# Run tests with verbose output
test-v *args:
    just test "-v" {{args}}

# Internal: check venv exists
[private]
venv-check:
    @test -d {{venv}} || (echo "Virtual environment not found at {{venv}}" && exit 1)
