# Release Notes 0.4.2

This compatibility patch fixes frozen runtime execution under Windows PowerShell
5.1. The shared process helper now uses `EnvironmentVariables`, implements the
Windows CRT command-line quoting algorithm, and never depends on `ArgumentList`.

Credential smoke tests, rehearsals, and formal launchers now require the frozen
`release_python`, use `release_root` as the working directory, run Python with
`-I`, clear `PYTHONPATH` and `PYTHONHOME`, verify release integrity, and reject a
module import outside the release venv.

No scientific target, Theme, model, threshold, position, order, or historical
result changed. Formal Data Shadow remains stopped.
