import argparse
import json
import math
import os
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path


APP_NAME = "Azurefrost Space Program"
EARTH_RADIUS_KM = 6371.0
EARTH_MU_KM3_S2 = 398600.4418
DEFAULT_VEHICLES = [
    {"name": "Aurora I", "payload_kg": 12000, "cost_musd": 48.0, "reusable": False},
    {"name": "Borealis Heavy", "payload_kg": 42000, "cost_musd": 115.0, "reusable": False},
    {"name": "Cirrus Reusable", "payload_kg": 18000, "cost_musd": 62.0, "reusable": True},
]
MISSION_STATUSES = ("planned", "ready", "launched", "completed", "cancelled")
TYPEWRITER_DELAY = 0.012


def typewrite(*values, sep=" ", end="\n", file=None, flush=False):
    stream = file or sys.stdout
    message = sep.join(str(value) for value in values) + end
    try:
        delay = min(0.1, max(0.0, float(os.environ.get("AZUREFROST_TYPE_DELAY", TYPEWRITER_DELAY))))
    except ValueError:
        delay = TYPEWRITER_DELAY
    if delay and getattr(stream, "isatty", lambda: False)():
        for character in message:
            stream.write(character)
            stream.flush()
            if character not in "\r\n":
                time.sleep(delay)
    else:
        stream.write(message)
    if flush:
        stream.flush()


def ask(prompt):
    typewrite(prompt, end="", flush=True)
    value = sys.stdin.readline()
    if value == "":
        raise EOFError
    return value.rstrip("\r\n")


def clear_terminal():
    if not getattr(sys.stdout, "isatty", lambda: False)():
        return
    if os.name == "nt":
        result = os.system("cls")
        if result == 0:
            return
    elif os.environ.get("TERM"):
        result = os.system("clear")
        if result == 0:
            return
    sys.stdout.write("\033[2J\033[H")
    sys.stdout.flush()


class TypewriterArgumentParser(argparse.ArgumentParser):
    def _print_message(self, message, file=None):
        if message:
            typewrite(message, end="", file=file or sys.stdout)


def default_data_path():
    if os.name == "nt":
        configured = os.environ.get("APPDATA")
        base = Path(configured) if configured else Path.home() / "AppData" / "Roaming"
    else:
        configured = os.environ.get("XDG_DATA_HOME")
        base = Path(configured) if configured else Path.home() / ".local" / "share"
    return base / "azurefrost-space-program" / "program.json"


def empty_store():
    return {"missions": [], "vehicles": list(DEFAULT_VEHICLES)}


def load_store(path):
    try:
        with path.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except FileNotFoundError:
        return empty_store()
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as error:
        raise ValueError(f"Could not read program data at {path}: {error}") from error
    if not isinstance(data, dict):
        raise ValueError(f"Program data at {path} has an invalid format.")
    missions = data.setdefault("missions", [])
    vehicles = data.setdefault("vehicles", list(DEFAULT_VEHICLES))
    if not isinstance(missions, list) or not isinstance(vehicles, list):
        raise ValueError(f"Program data at {path} has an invalid format.")
    identifiers = set()
    for mission in missions:
        if not isinstance(mission, dict):
            raise ValueError(f"Program data at {path} has an invalid mission entry.")
        required = ("id", "name", "destination", "payload_kg", "altitude_km", "status")
        if any(key not in mission for key in required):
            raise ValueError(f"A mission in {path} is missing required fields.")
        if isinstance(mission["id"], bool) or not isinstance(mission["id"], int) or mission["id"] <= 0 or mission["id"] in identifiers:
            raise ValueError(f"Mission IDs in {path} must be unique positive integers.")
        identifiers.add(mission["id"])
        if not all(isinstance(mission[key], str) for key in ("name", "destination", "status")):
            raise ValueError(f"A mission in {path} has invalid text fields.")
        if mission["status"] not in MISSION_STATUSES:
            raise ValueError(f"A mission in {path} has an unknown status.")
        for key in ("payload_kg", "altitude_km"):
            if isinstance(mission[key], bool) or not isinstance(mission[key], (int, float)) or not math.isfinite(mission[key]):
                raise ValueError(f"A mission in {path} has an invalid {key} value.")
        if mission["payload_kg"] <= 0 or mission["altitude_km"] < 0 or mission["altitude_km"] > 1_000_000:
            raise ValueError(f"A mission in {path} has an out-of-range payload or altitude.")
    for vehicle in vehicles:
        if not isinstance(vehicle, dict) or not isinstance(vehicle.get("name"), str):
            raise ValueError(f"A launch vehicle in {path} has invalid data.")
        for key in ("payload_kg", "cost_musd"):
            value = vehicle.get(key)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
                raise ValueError(f"A launch vehicle in {path} has an invalid {key} value.")
        if "reusable" in vehicle and not isinstance(vehicle["reusable"], bool):
            raise ValueError(f"A launch vehicle in {path} has an invalid reusable value.")
    return data


def save_store(path, data):
    temporary = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", newline="\n", dir=path.parent,
            prefix=path.name + ".", suffix=".tmp", delete=False,
        ) as file:
            temporary = Path(file.name)
            json.dump(data, file, indent=2, ensure_ascii=False, allow_nan=False)
            file.write("\n")
        temporary.replace(path)
    except (OSError, TypeError, ValueError) as error:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
        raise ValueError(f"Could not save program data at {path}: {error}") from error


def orbital_speed(altitude_km):
    radius = EARTH_RADIUS_KM + altitude_km
    return math.sqrt(EARTH_MU_KM3_S2 / radius)


def orbital_period(altitude_km):
    radius = EARTH_RADIUS_KM + altitude_km
    return 2 * math.pi * math.sqrt(radius**3 / EARTH_MU_KM3_S2)


def transfer_delta_v(altitude_km):
    parking_radius = EARTH_RADIUS_KM + 200
    target_radius = EARTH_RADIUS_KM + altitude_km
    if target_radius == parking_radius:
        return 0.0
    first_burn = math.sqrt(EARTH_MU_KM3_S2 / parking_radius) * (
        math.sqrt(2 * target_radius / (parking_radius + target_radius)) - 1
    )
    second_burn = math.sqrt(EARTH_MU_KM3_S2 / target_radius) * (
        1 - math.sqrt(2 * parking_radius / (parking_radius + target_radius))
    )
    return abs(first_burn) + abs(second_burn)


def print_table(headers, rows):
    if not rows:
        typewrite("Nothing to show yet.")
        return
    widths = [len(str(header)) for header in headers]
    for row in rows:
        for index, value in enumerate(row):
            widths[index] = max(widths[index], len(str(value)))
    typewrite("  ".join(str(value).ljust(widths[index]) for index, value in enumerate(headers)))
    typewrite("  ".join("-" * width for width in widths))
    for row in rows:
        typewrite("  ".join(str(value).ljust(widths[index]) for index, value in enumerate(row)))


def find_mission(data, mission_id):
    return next((mission for mission in data["missions"] if mission["id"] == mission_id), None)


def next_mission_id(data):
    return max((mission.get("id", 0) for mission in data["missions"]), default=0) + 1


def create_mission(data, name, destination, payload, altitude):
    name = name.strip()
    destination = destination.strip()
    if not name or not destination:
        raise ValueError("Mission name and destination cannot be empty.")
    if not math.isfinite(payload) or not math.isfinite(altitude) or payload <= 0 or altitude < 0 or altitude > 1_000_000:
        raise ValueError("Payload must be positive and altitude must be between 0 and 1,000,000 kilometers.")
    mission = {
        "id": next_mission_id(data),
        "name": name,
        "destination": destination,
        "payload_kg": payload,
        "altitude_km": altitude,
        "status": "planned",
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    data["missions"].append(mission)
    return mission


def add_mission(data, data_path, name, destination, payload, altitude):
    mission = create_mission(data, name, destination, payload, altitude)
    try:
        save_store(data_path, data)
    except ValueError:
        data["missions"].remove(mission)
        raise
    return mission


def update_mission_status(data, data_path, mission_id, status):
    mission = find_mission(data, mission_id)
    if mission is None:
        raise ValueError(f"Mission {mission_id} was not found.")
    previous = dict(mission)
    mission["status"] = status
    mission["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    try:
        save_store(data_path, data)
    except ValueError:
        mission.clear()
        mission.update(previous)
        raise
    return mission


def delete_mission(data, data_path, mission_id):
    mission = find_mission(data, mission_id)
    if mission is None:
        raise ValueError(f"Mission {mission_id} was not found.")
    original_index = data["missions"].index(mission)
    data["missions"].remove(mission)
    try:
        save_store(data_path, data)
    except ValueError:
        data["missions"].insert(original_index, mission)
        raise
    return mission


def handle_status(data, args):
    missions = data["missions"]
    typewrite(APP_NAME)
    typewrite(f"Missions: {len(missions)}  |  Vehicles: {len(data['vehicles'])}")
    for status in MISSION_STATUSES:
        count = sum(mission.get("status") == status for mission in missions)
        typewrite(f"{status.title():10} {count}")


def handle_missions(data, args):
    if args.mission_action == "list":
        rows = [
            (mission["id"], mission["name"], mission["destination"], mission["status"],
             f"{mission['payload_kg']:,.0f} kg", f"{mission['altitude_km']:,.0f} km")
            for mission in sorted(data["missions"], key=lambda item: item["id"])
        ]
        print_table(("ID", "Mission", "Destination", "Status", "Payload", "Orbit"), rows)
        return
    if args.mission_action == "add":
        mission = add_mission(data, args.data, args.name, args.destination, args.payload, args.altitude)
        typewrite(f"Added mission {mission['id']}: {mission['name']}.")
        return
    if args.mission_action == "delete":
        mission = delete_mission(data, args.data, args.id)
        typewrite(f"Deleted mission {args.id}: {mission['name']}.")
        return
    mission = find_mission(data, args.id)
    if mission is None:
        raise ValueError(f"Mission {args.id} was not found.")
    if args.mission_action == "show":
        for key, value in mission.items():
            typewrite(f"{key.replace('_', ' ').title()}: {value}")
        return
    update_mission_status(data, args.data, args.id, args.status)
    typewrite(f"Mission {args.id} status set to {args.status}.")


def handle_vehicles(data, args):
    rows = [
        (vehicle["name"], f"{vehicle['payload_kg']:,.0f} kg", f"${vehicle['cost_musd']:,.1f}M",
         "Yes" if vehicle.get("reusable") else "No")
        for vehicle in data["vehicles"]
    ]
    print_table(("Vehicle", "LEO payload", "Estimated cost", "Reusable"), rows)


def handle_orbit(data, args):
    if not math.isfinite(args.altitude) or args.altitude < 0 or args.altitude > 1_000_000:
        raise ValueError("Altitude must be between 0 and 1,000,000 kilometers.")
    speed = orbital_speed(args.altitude)
    period_minutes = orbital_period(args.altitude) / 60
    delta_v = transfer_delta_v(args.altitude)
    typewrite(f"Circular orbital speed: {speed:.3f} km/s")
    typewrite(f"Orbital period: {period_minutes:.1f} minutes ({period_minutes / 60:.2f} hours)")
    typewrite(f"Ideal Hohmann transfer from 200 km: {delta_v * 1000:.0f} m/s")


def handle_vehicles_select(data, args):
    mission = find_mission(data, args.mission_id)
    if mission is None:
        raise ValueError(f"Mission {args.mission_id} was not found.")
    candidates = [vehicle for vehicle in data["vehicles"] if vehicle["payload_kg"] >= mission["payload_kg"]]
    candidates.sort(key=lambda vehicle: (vehicle["cost_musd"], vehicle["payload_kg"]))
    if not candidates:
        typewrite(f"No listed vehicle can carry {mission['payload_kg']:,.0f} kg.")
        return
    typewrite(f"Recommended vehicle for {mission['name']}: {candidates[0]['name']}")
    typewrite(f"Estimated launch cost: ${candidates[0]['cost_musd']:,.1f}M")
    typewrite("Payload capacity is a simplified low Earth orbit estimate.")


def handle_checklist(data, args):
    mission = find_mission(data, args.mission_id)
    if mission is None:
        raise ValueError(f"Mission {args.mission_id} was not found.")
    candidates = [vehicle for vehicle in data["vehicles"] if vehicle["payload_kg"] >= mission["payload_kg"]]
    items = [
        ("Mission details recorded", bool(mission["name"] and mission["destination"])),
        ("Payload mass is valid", mission["payload_kg"] > 0),
        ("Launch vehicle can carry payload", bool(candidates)),
        ("Mission marked ready", mission["status"] == "ready"),
    ]
    typewrite(f"Launch readiness: {mission['name']}")
    for label, passed in items:
        typewrite(f"{'[x]' if passed else '[ ]'} {label}")
    typewrite("READY FOR LAUNCH" if all(passed for _, passed in items) else "NOT READY")


def make_parser():
    parser = TypewriterArgumentParser(prog="azurefrost", description="Portable space mission planning console")
    parser.add_argument("--data", type=Path, default=default_data_path(), help="Path to the JSON program data file")
    commands = parser.add_subparsers(dest="command", parser_class=TypewriterArgumentParser)
    commands.add_parser("status", help="Show program activity")
    missions = commands.add_parser("missions", help="Manage missions")
    mission_commands = missions.add_subparsers(dest="mission_action", required=True)
    mission_commands.add_parser("list", help="List all missions")
    add = mission_commands.add_parser("add", help="Create a mission")
    add.add_argument("name")
    add.add_argument("--destination", default="Low Earth Orbit")
    add.add_argument("--payload", type=float, required=True, help="Payload mass in kilograms")
    add.add_argument("--altitude", type=float, default=400, help="Target altitude in kilometers")
    show = mission_commands.add_parser("show", help="Show mission details")
    show.add_argument("id", type=int)
    update = mission_commands.add_parser("status", help="Update mission status")
    update.add_argument("id", type=int)
    update.add_argument("status", choices=MISSION_STATUSES)
    delete = mission_commands.add_parser("delete", help="Delete a mission")
    delete.add_argument("id", type=int)
    commands.add_parser("vehicles", help="List launch vehicles")
    orbit = commands.add_parser("orbit", help="Calculate a circular Earth orbit")
    orbit.add_argument("altitude", type=float, help="Altitude above Earth's surface in kilometers")
    recommend = commands.add_parser("recommend", help="Find a vehicle for a mission")
    recommend.add_argument("mission_id", type=int)
    checklist = commands.add_parser("checklist", help="Check launch readiness for a mission")
    checklist.add_argument("mission_id", type=int)
    commands.add_parser("clear", help="Clear the terminal")
    return parser


def interactive(data, data_path):
    clear_terminal()
    while True:
        typewrite(f"\n{APP_NAME}")
        typewrite("1. Program status")
        typewrite("2. List missions")
        typewrite("3. Add mission")
        typewrite("4. List launch vehicles")
        typewrite("5. Calculate an orbit")
        typewrite("6. Recommend a vehicle")
        typewrite("7. Launch readiness checklist")
        typewrite("8. Update mission status")
        typewrite("9. Delete a mission")
        typewrite("C. Clear terminal")
        typewrite("0. Exit")
        try:
            choice = ask("Select an option: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            typewrite("\nGoodbye.")
            return 0
        try:
            if choice == "0":
                typewrite("Goodbye.")
                return 0
            if choice == "1":
                handle_status(data, None)
            elif choice == "2":
                print_table(
                    ("ID", "Mission", "Destination", "Status", "Payload", "Orbit"),
                    [(mission["id"], mission["name"], mission["destination"], mission["status"],
                      f"{mission['payload_kg']:,.0f} kg", f"{mission['altitude_km']:,.0f} km")
                     for mission in sorted(data["missions"], key=lambda item: item["id"])],
                )
            elif choice == "3":
                name = ask("Mission name: ").strip()
                destination = ask("Destination [Low Earth Orbit]: ").strip() or "Low Earth Orbit"
                payload = float(ask("Payload mass in kilograms: ").strip())
                altitude = float(ask("Target altitude in kilometers [400]: ").strip() or "400")
                mission = add_mission(data, data_path, name, destination, payload, altitude)
                typewrite(f"Added mission {mission['id']}: {mission['name']}.")
            elif choice == "4":
                handle_vehicles(data, None)
            elif choice == "5":
                altitude = float(ask("Orbit altitude in kilometers: ").strip())
                handle_orbit(data, argparse.Namespace(altitude=altitude))
            elif choice == "6":
                mission_id = int(ask("Mission ID: ").strip())
                handle_vehicles_select(data, argparse.Namespace(mission_id=mission_id))
            elif choice == "7":
                mission_id = int(ask("Mission ID: ").strip())
                handle_checklist(data, argparse.Namespace(mission_id=mission_id))
            elif choice == "8":
                mission_id = int(ask("Mission ID: ").strip())
                status = ask(f"New status {MISSION_STATUSES}: ").strip().lower()
                if status not in MISSION_STATUSES:
                    raise ValueError("Choose one of the listed mission statuses.")
                mission = find_mission(data, mission_id)
                if mission is None:
                    raise ValueError(f"Mission {mission_id} was not found.")
                update_mission_status(data, data_path, mission_id, status)
                typewrite(f"Mission {mission_id} status set to {status}.")
            elif choice == "9":
                mission_id = int(ask("Mission ID to delete: ").strip())
                mission = find_mission(data, mission_id)
                if mission is None:
                    raise ValueError(f"Mission {mission_id} was not found.")
                confirmation = ask(f"Delete {mission['name']}? Type yes to confirm: ").strip().lower()
                if confirmation == "yes":
                    delete_mission(data, data_path, mission_id)
                    typewrite(f"Deleted mission {mission_id}.")
                else:
                    typewrite("Deletion cancelled.")
            elif choice == "c":
                clear_terminal()
            else:
                typewrite("Choose one of the listed options.")
        except (ValueError, KeyError, TypeError) as error:
            typewrite(f"Error: {error}")
        except (EOFError, KeyboardInterrupt):
            typewrite("\nAction cancelled.")
        try:
            ask("\nPress Enter to continue...")
        except (EOFError, KeyboardInterrupt):
            typewrite("\nGoodbye.")
            return 0
        clear_terminal()


def main(argv=None):
    parser = make_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "clear":
            clear_terminal()
            typewrite("Terminal cleared.")
            return 0
        data = load_store(args.data)
        if args.command is None:
            return interactive(data, args.data)
        handlers = {
            "status": handle_status,
            "missions": handle_missions,
            "vehicles": handle_vehicles,
            "orbit": handle_orbit,
            "recommend": handle_vehicles_select,
            "checklist": handle_checklist,
        }
        if args.command == "missions" and args.mission_action == "delete":
            mission = delete_mission(data, args.data, args.id)
            typewrite(f"Deleted mission {args.id}: {mission['name']}.")
        else:
            handlers[args.command](data, args)
    except (ValueError, KeyError, TypeError) as error:
        typewrite(f"Error: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
