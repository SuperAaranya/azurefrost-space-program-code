# azurefrost-space-program-code

Azurefrost Space Program is a small, portable command-line mission planning console. It uses only Python's standard library and runs on Windows, macOS, and Linux.

## Run

Use Python 3.9 or newer:

```text
python main.py
```

Running without arguments opens the interactive planning menu. Add `--help` to see the command-line options.

On systems where Python is installed as `python3`, use `python3 main.py` instead.

## Commands

```text
python main.py status
python main.py vehicles
python main.py missions add "Europa Mapper" --destination Europa --payload 2400 --altitude 500
python main.py missions list
python main.py missions show 1
python main.py recommend 1
python main.py missions status 1 ready
python main.py orbit 400
```

Mission records are stored as JSON in the operating system's user data directory. Pass `--data path/to/program.json` before the command to choose another location, which is useful for portable copies and separate planning files.

Orbit calculations assume a spherical Earth and ideal two-body motion. Launch vehicle capacities and costs are illustrative planning estimates.
