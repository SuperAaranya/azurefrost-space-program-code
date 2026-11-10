import argparse
import json
import math
import os
import sys
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


def default_data_path():
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / "azurefrost-space-program" / "program.json"


def empty_store():
    return {"missions": [], "vehicles": list(DEFAULT_VEHICLES)}


def load_store(path):
    try:
        with path.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except FileNotFoundError:
        return empty_store()
    except (json.JSONDecodeError, OSError) as error:
        raise ValueError(f"Could not read program data at {path}: {error}") from error
    if not isinstance(data, dict):
        raise ValueError(f"Program data at {path} has an invalid format.")
    data.setdefault("missions", [])
    data.setdefault("vehicles", list(DEFAULT_VEHICLES))
    if not isinstance(data["missions"], list) or not isinstance(data["vehicles"], list):
        raise ValueError(f"Program data at {path} has an invalid format.")
    return data


def save_store(path, data):
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(path.name + ".tmp")
        with temporary.open("w", encoding="utf-8", newline="\n") as file:
            json.dump(data, file, indent=2, ensure_ascii=False)
            file.write("\n")
        temporary.replace(path)
    except OSError as error:
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
        print("Nothing to show yet.")
        return
    widths = [len(str(header)) for header in headers]
    for row in rows:
        for index, value in enumerate(row):
            widths[index] = max(widths[index], len(str(value)))
    print("  ".join(str(value).ljust(widths[index]) for index, value in enumerate(headers)))
    print("  ".join("-" * width for width in widths))
    for row in rows:
        print("  ".join(str(value).ljust(widths[index]) for index, value in enumerate(row)))


def find_mission(data, mission_id):
    return next((mission for mission in data["missions"] if mission["id"] == mission_id), None)


def next_mission_id(data):
    return max((mission.get("id", 0) for mission in data["missions"]), default=0) + 1


def handle_status(data, args):
    missions = data["missions"]
    print(APP_NAME)
    print(f"Missions: {len(missions)}  |  Vehicles: {len(data['vehicles'])}")
    for status in MISSION_STATUSES:
        count = sum(mission.get("status") == status for mission in missions)
        print(f"{status.title():10} {count}")


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
        if args.payload <= 0 or args.altitude < 0:
            raise ValueError("Payload must be positive and altitude cannot be negative.")
        mission = {
            "id": next_mission_id(data),
            "name": args.name,
            "destination": args.destination,
            "payload_kg": args.payload,
            "altitude_km": args.altitude,
            "status": "planned",
            "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        data["missions"].append(mission)
        save_store(args.data, data)
        print(f"Added mission {mission['id']}: {mission['name']}.")
        return
    mission = find_mission(data, args.id)
    if mission is None:
        raise ValueError(f"Mission {args.id} was not found.")
    if args.mission_action == "show":
        for key, value in mission.items():
            print(f"{key.replace('_', ' ').title()}: {value}")
        return
    mission["status"] = args.status
    mission["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    save_store(args.data, data)
    print(f"Mission {args.id} status set to {args.status}.")


def handle_vehicles(data, args):
    rows = [
        (vehicle["name"], f"{vehicle['payload_kg']:,.0f} kg", f"${vehicle['cost_musd']:,.1f}M",
         "Yes" if vehicle.get("reusable") else "No")
        for vehicle in data["vehicles"]
    ]
    print_table(("Vehicle", "LEO payload", "Estimated cost", "Reusable"), rows)


def handle_orbit(data, args):
    if args.altitude < 0:
        raise ValueError("Altitude cannot be negative.")
    speed = orbital_speed(args.altitude)
    period_minutes = orbital_period(args.altitude) / 60
    delta_v = transfer_delta_v(args.altitude)
    print(f"Circular orbital speed: {speed:.3f} km/s")
    print(f"Orbital period: {period_minutes:.1f} minutes ({period_minutes / 60:.2f} hours)")
    print(f"Ideal Hohmann transfer from 200 km: {delta_v * 1000:.0f} m/s")


def handle_vehicles_select(data, args):
    mission = find_mission(data, args.mission_id)
    if mission is None:
        raise ValueError(f"Mission {args.mission_id} was not found.")
    candidates = [vehicle for vehicle in data["vehicles"] if vehicle["payload_kg"] >= mission["payload_kg"]]
    candidates.sort(key=lambda vehicle: (vehicle["cost_musd"], vehicle["payload_kg"]))
    if not candidates:
        print(f"No listed vehicle can carry {mission['payload_kg']:,.0f} kg.")
        return
    print(f"Recommended vehicle for {mission['name']}: {candidates[0]['name']}")
    print(f"Estimated launch cost: ${candidates[0]['cost_musd']:,.1f}M")
    print("Payload capacity is a simplified low Earth orbit estimate.")


def make_parser():
    parser = argparse.ArgumentParser(prog="azurefrost", description="Portable space mission planning console")
    parser.add_argument("--data", type=Path, default=default_data_path(), help="Path to the JSON program data file")
    commands = parser.add_subparsers(dest="command", required=True)
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
    commands.add_parser("vehicles", help="List launch vehicles")
    orbit = commands.add_parser("orbit", help="Calculate a circular Earth orbit")
    orbit.add_argument("altitude", type=float, help="Altitude above Earth's surface in kilometers")
    recommend = commands.add_parser("recommend", help="Find a vehicle for a mission")
    recommend.add_argument("mission_id", type=int)
    return parser


def main(argv=None):
    parser = make_parser()
    args = parser.parse_args(argv)
    try:
        data = load_store(args.data)
        handlers = {
            "status": handle_status,
            "missions": handle_missions,
            "vehicles": handle_vehicles,
            "orbit": handle_orbit,
            "recommend": handle_vehicles_select,
        }
        handlers[args.command](data, args)
    except (ValueError, KeyError, TypeError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
