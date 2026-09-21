#!/usr/bin/env python3
"""Independently verify schematic and PCB physical-pin connectivity."""

from __future__ import annotations

import argparse
import math
import re
import sys
from pathlib import Path
from typing import Iterable, Union


Atom = str
SExpr = list[Union[Atom, "SExpr"]]
ROOT = Path(__file__).resolve().parents[1]
PROJECT = "compute-blade-dda-adapter"
SCH_PATH = ROOT / "pcb" / f"{PROJECT}.kicad_sch"
PCB_PATH = ROOT / "pcb" / f"{PROJECT}.kicad_pcb"

EXPECTED_GROUPS = [
    {"J1.1", "J2.1"},
    {"J1.2", "J2.2"},
    {"J1.3", "J2.3"},
    {"J1.4", "J2.4"},
    {"J1.5", "J2.5"},
    {"J1.6", "J2.6"},
    {"J1.7", "J2.7", "J2.12"},
    {"J1.8", "J2.8"},
    {"J1.9", "J2.9"},
    {"J1.10", "J2.10"},
]
EXPECTED_PINS = {pin for group in EXPECTED_GROUPS for pin in group} | {"J2.11"}
POWER = {
    "3V3": {"J1.1", "J2.1"},
    "5V": {"J1.2", "J2.2", "J1.4", "J2.4"},
    "GND": {"J1.6", "J2.6", "J1.9", "J2.9"},
}
GPIO_PINS = {
    "J1.3", "J2.3", "J1.5", "J2.5", "J1.7", "J2.7", "J2.12",
    "J1.8", "J2.8", "J1.10", "J2.10",
}


def tokenize(text: str) -> list[str]:
    pattern = re.compile(r'\s*(?:;[^\n]*|("(?:\\.|[^"\\])*")|([()]|[^\s()]+))')
    result = []
    for match in pattern.finditer(text):
        token = match.group(1) or match.group(2)
        if token is None:
            continue
        if token.startswith('"'):
            token = bytes(token[1:-1], "utf-8").decode("unicode_escape")
        result.append(token)
    return result


def parse_sexpr(text: str) -> SExpr:
    tokens = tokenize(text)
    stack: list[SExpr] = []
    root: SExpr = []
    current = root
    for token in tokens:
        if token == "(":
            node: SExpr = []
            current.append(node)
            stack.append(current)
            current = node
        elif token == ")":
            if not stack:
                raise ValueError("unmatched closing parenthesis")
            current = stack.pop()
        else:
            current.append(token)
    if stack:
        raise ValueError("unclosed parenthesis")
    if len(root) != 1 or not isinstance(root[0], list):
        raise ValueError("expected exactly one root expression")
    return root[0]


def children(node: SExpr, head: str) -> list[SExpr]:
    return [item for item in node if isinstance(item, list) and item and item[0] == head]


def child(node: SExpr, head: str) -> SExpr | None:
    found = children(node, head)
    return found[0] if found else None


def atom(node: SExpr, head: str, index: int = 1) -> str:
    item = child(node, head)
    if item is None or len(item) <= index or not isinstance(item[index], str):
        raise ValueError(f"missing {head}")
    return item[index]


def xy(node: SExpr, head: str = "at") -> tuple[float, float]:
    item = child(node, head)
    if item is None or len(item) < 3:
        raise ValueError(f"missing coordinates for {head}")
    return round(float(item[1]), 3), round(float(item[2]), 3)


def properties(node: SExpr) -> dict[str, str]:
    result = {}
    for item in children(node, "property"):
        if len(item) >= 3 and isinstance(item[1], str) and isinstance(item[2], str):
            result[item[1]] = item[2]
    return result


def schematic_pin_nets(path: Path) -> dict[str, str | None]:
    tree = parse_sexpr(path.read_text(encoding="utf-8"))
    lib_root = child(tree, "lib_symbols")
    if lib_root is None:
        raise ValueError("schematic has no lib_symbols")

    lib_pins: dict[str, dict[str, tuple[float, float]]] = {}
    for symbol in children(lib_root, "symbol"):
        if len(symbol) < 2 or not isinstance(symbol[1], str):
            continue
        pin_map: dict[str, tuple[float, float]] = {}
        for unit in children(symbol, "symbol"):
            for pin in children(unit, "pin"):
                number_node = child(pin, "number")
                if number_node and len(number_node) > 1:
                    pin_map[str(number_node[1])] = xy(pin)
        lib_pins[symbol[1]] = pin_map

    labels = {xy(item): str(item[1]) for item in children(tree, "label")}
    no_connects = {xy(item) for item in children(tree, "no_connect")}
    result: dict[str, str | None] = {}
    for symbol in children(tree, "symbol"):
        lib_id_node = child(symbol, "lib_id")
        if lib_id_node is None:
            continue
        props = properties(symbol)
        ref = props.get("Reference", "")
        if ref not in {"J1", "J2"}:
            continue
        lib_id = str(lib_id_node[1])
        sx, sy = xy(symbol)
        for pin, (px, py) in lib_pins[lib_id].items():
            location = (round(sx + px, 3), round(sy + py, 3))
            key = f"{ref}.{pin}"
            if location in labels:
                result[key] = labels[location]
            elif location in no_connects:
                result[key] = None
            else:
                result[key] = "<UNCONNECTED_WITHOUT_NC_FLAG>"
    return result


def pcb_pin_nets(path: Path) -> dict[str, str | None]:
    tree = parse_sexpr(path.read_text(encoding="utf-8"))
    result: dict[str, str | None] = {}
    for footprint in children(tree, "footprint"):
        props = properties(footprint)
        ref = props.get("Reference")
        if ref not in {"J1", "J2"}:
            continue
        for pad in children(footprint, "pad"):
            pin = str(pad[1])
            net_node = child(pad, "net")
            net = None
            if net_node is not None and len(net_node) >= 3:
                net = str(net_node[2])
            result[f"{ref}.{pin}"] = net
    return result


class DisjointSet:
    def __init__(self) -> None:
        self.parent: dict[tuple[float, float, str], tuple[float, float, str]] = {}

    def add(self, item: tuple[float, float, str]) -> None:
        self.parent.setdefault(item, item)

    def find(self, item: tuple[float, float, str]) -> tuple[float, float, str]:
        self.add(item)
        if self.parent[item] != item:
            self.parent[item] = self.find(self.parent[item])
        return self.parent[item]

    def union(self, left: tuple[float, float, str], right: tuple[float, float, str]) -> None:
        left_root = self.find(left)
        right_root = self.find(right)
        if left_root != right_root:
            self.parent[right_root] = left_root


def transformed_pad(footprint: SExpr, pad: SExpr) -> tuple[float, float]:
    footprint_at = child(footprint, "at")
    if footprint_at is None:
        raise ValueError("footprint has no position")
    ox, oy = float(footprint_at[1]), float(footprint_at[2])
    angle = float(footprint_at[3]) if len(footprint_at) > 3 else 0.0
    px, py = xy(pad)
    radians = math.radians(angle)
    # KiCad board coordinates are Y-down, so footprint rotation uses the
    # inverse sign of the conventional Cartesian XY matrix.
    gx = ox + math.cos(radians) * px + math.sin(radians) * py
    gy = oy - math.sin(radians) * px + math.cos(radians) * py
    return round(gx, 3), round(gy, 3)


def validate_pcb_routing(path: Path) -> list[str]:
    """Confirm copper segments physically reach every assigned connector pad."""
    tree = parse_sexpr(path.read_text(encoding="utf-8"))
    code_to_net = {
        int(item[1]): str(item[2]) for item in children(tree, "net") if len(item) >= 3
    }
    dsu_by_net: dict[str, DisjointSet] = {}
    segment_nodes: dict[str, set[tuple[float, float, str]]] = {}

    for item in children(tree, "segment"):
        code = int(atom(item, "net"))
        if code not in code_to_net:
            return [f"PCB route uses undefined net code {code}"]
        net = code_to_net[code]
        layer = atom(item, "layer")
        start_xy = xy(item, "start")
        end_xy = xy(item, "end")
        start = (*start_xy, layer)
        end = (*end_xy, layer)
        dsu = dsu_by_net.setdefault(net, DisjointSet())
        dsu.union(start, end)
        segment_nodes.setdefault(net, set()).update((start, end))

    pin_nodes: dict[str, tuple[str, tuple[float, float, str]]] = {}
    errors: list[str] = []
    for footprint in children(tree, "footprint"):
        ref = properties(footprint).get("Reference")
        if ref not in {"J1", "J2"}:
            continue
        for pad in children(footprint, "pad"):
            pin = f"{ref}.{pad[1]}"
            net_node = child(pad, "net")
            if net_node is None:
                continue
            net = str(net_node[2])
            location = transformed_pad(footprint, pad)
            front = (*location, "F.Cu")
            back = (*location, "B.Cu")
            dsu = dsu_by_net.setdefault(net, DisjointSet())
            dsu.union(front, back)  # A plated through-hole pad connects both layers.
            pin_nodes[pin] = (net, front)
            touching = segment_nodes.get(net, set())
            if front not in touching and back not in touching:
                errors.append(f"PCB: {pin} ({net}) has no routed segment at pad {location}")

    for group in EXPECTED_GROUPS:
        roots = set()
        for pin in group:
            if pin not in pin_nodes:
                continue
            net, node = pin_nodes[pin]
            roots.add((net, dsu_by_net[net].find(node)))
        if len(roots) != 1:
            errors.append(f"PCB: routed copper does not join {sorted(group)}")
    return errors


def validate(pin_nets: dict[str, str | None], source: str) -> list[str]:
    errors = []
    missing = EXPECTED_PINS - pin_nets.keys()
    extra = pin_nets.keys() - EXPECTED_PINS
    if missing:
        errors.append(f"{source}: missing pins: {', '.join(sorted(missing))}")
    if extra:
        errors.append(f"{source}: unexpected pins: {', '.join(sorted(extra))}")

    for expected in EXPECTED_GROUPS:
        nets = {pin_nets.get(pin) for pin in expected}
        if None in nets or "<UNCONNECTED_WITHOUT_NC_FLAG>" in nets or len(nets) != 1:
            errors.append(f"{source}: expected one net for {sorted(expected)}, got {sorted(map(str, nets))}")

    # Exact means different requested groups may not be merged.
    seen: dict[str, set[str]] = {}
    for group in EXPECTED_GROUPS:
        net = pin_nets.get(next(iter(group)))
        if net is not None:
            seen.setdefault(net, set()).update(group)
    for net, pins in seen.items():
        matching = [group for group in EXPECTED_GROUPS if group <= pins]
        if len(matching) > 1:
            errors.append(f"{source}: net {net!r} improperly merges groups: {sorted(pins)}")

    if pin_nets.get("J2.11", "missing") is not None:
        errors.append(f"{source}: J2.11 must be NC, got {pin_nets.get('J2.11')!r}")

    power_nets = {kind: {pin_nets.get(pin) for pin in pins} - {None} for kind, pins in POWER.items()}
    for left, right in (("3V3", "5V"), ("3V3", "GND"), ("5V", "GND")):
        overlap = power_nets[left] & power_nets[right]
        if overlap:
            errors.append(f"{source}: {left} is shorted to {right} on {sorted(overlap)}")
    rails = set().union(*power_nets.values())
    for pin in sorted(GPIO_PINS):
        if pin_nets.get(pin) in rails:
            errors.append(f"{source}: GPIO pin {pin} is shorted to power rail {pin_nets[pin]!r}")
    return errors


def print_table(maps: Iterable[tuple[str, dict[str, str | None]]]) -> None:
    maps = list(maps)
    headings = [name for name, _ in maps]
    print(f"{'Pin':<7}" + "".join(f"{name:<28}" for name in headings))
    print("-" * (7 + 28 * len(headings)))
    ordered = [f"J1.{n}" for n in range(1, 11)] + [f"J2.{n}" for n in range(1, 13)]
    for pin in ordered:
        values = []
        for _, mapping in maps:
            value = mapping.get(pin, "<MISSING>")
            values.append("NC" if value is None else str(value))
        print(f"{pin:<7}" + "".join(f"{value:<28}" for value in values))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--schematic-only", action="store_true", help="validate before the PCB exists")
    args = parser.parse_args()

    try:
        schematic = schematic_pin_nets(SCH_PATH)
        maps = [("Schematic", schematic)]
        errors = validate(schematic, "schematic")
        if not args.schematic_only:
            pcb = pcb_pin_nets(PCB_PATH)
            maps.append(("PCB", pcb))
            errors.extend(validate(pcb, "PCB"))
            errors.extend(validate_pcb_routing(PCB_PATH))
            for pin in sorted(EXPECTED_PINS):
                if schematic.get(pin) != pcb.get(pin):
                    errors.append(
                        f"schematic/PCB mismatch at {pin}: {schematic.get(pin)!r} != {pcb.get(pin)!r}"
                    )
        print_table(maps)
    except (OSError, ValueError, KeyError) as exc:
        print(f"ERROR: could not parse project: {exc}", file=sys.stderr)
        return 2

    if errors:
        print("\nCONNECTIVITY VERIFICATION FAILED", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print("\nConnectivity verification passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
