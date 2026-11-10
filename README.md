# azurefrost-space-program-code

Azurefrost Space Program is a small, portable command-line mission planning console. It uses only Python's standard library and runs on Windows, macOS, and Linux.

## Run

Use Python 3.9 or newer:

```text
python main.py
```

Running without arguments clears the terminal and opens the interactive planning menu. Menus, prompts, command output, and help use a typewriter effect in a terminal. Set the delay with `AZUREFROST_TYPE_DELAY` in seconds; use `env AZUREFROST_TYPE_DELAY=0 python main.py` to disable it. Output piped to another program is written without delays.

The clear action uses the native Windows command or the standard terminal clear command on Unix-like systems, with an ANSI fallback.

On systems where Python is installed as `python3`, use `python3 main.py` instead.

## Commands

```text
python main.py status
python main.py vehicles
python main.py missions add "Europa Mapper" --destination Europa --payload 2400 --altitude 500
python main.py missions list
python main.py missions show 1
python main.py missions delete 1
python main.py recommend 1
python main.py checklist 1
python main.py missions status 1 ready
python main.py orbit 400
python main.py clear
```

Mission records are stored as JSON in the operating system's user data directory. Pass `--data path/to/program.json` before the command to choose another location, which is useful for portable copies and separate planning files.

Orbit calculations assume a spherical Earth and ideal two-body motion. Supported mission orbit altitudes range from 0 to 1,000,000 km. Launch vehicle capacities and costs are illustrative planning estimates. Invalid or damaged JSON data produces a readable error instead of crashing during mission actions.
