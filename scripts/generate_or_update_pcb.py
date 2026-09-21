#!/usr/bin/env python3
"""Deterministically generate the routed two-connector KiCad PCB."""

from __future__ import annotations

import uuid
import math
import heapq
from functools import lru_cache
from pathlib import Path

from design_config import (
    BOARD_THICKNESS_MM,
    BOARD_BOUNDS_RELATIVE_J1_MM,
    J1_FOOTPRINT,
    J1_MODEL,
    J1_ORIGIN_MM,
    J2_FOOTPRINT,
    J2_FOOTPRINT_ROTATION_DEG,
    J2_MODEL,
    J2_ORIGIN_MM,
    J2_CENTERLINE_OFFSET_MM,
    PITCH_MM,
    POWER_TRACE_WIDTH_MM,
    SIGNAL_TRACE_WIDTH_MM,
)


ROOT = Path(__file__).resolve().parents[1]
BOARD_PATH = ROOT / "pcb" / "compute-blade-dda-adapter.kicad_pcb"
REPORT_PATH = ROOT / "CONNECTIVITY.txt"
UUID_NAMESPACE = uuid.UUID("5ec70a29-b9c1-44f3-96f8-6bd81180ce3d")

NET_BY_PIN = {
    1: "3V3", 2: "5V_PIN2", 3: "SDA_GPIO2", 4: "5V_PIN4",
    5: "SCL_GPIO3", 6: "GND_PIN6", 7: "PPS_GPIO4",
    8: "UART_TX_TO_GPS_RX", 9: "GND_PIN9", 10: "UART_RX_FROM_GPS_TX",
}
NET_CODE = {net: index for index, net in enumerate(NET_BY_PIN.values(), start=1)}
POWER_NETS = {"3V3", "5V_PIN2", "5V_PIN4", "GND_PIN6", "GND_PIN9"}
ROUTE_ORDER = (9, 7, 5, 3, 1, 10, 8, 6, 4)


def uid(name: str) -> str:
    return str(uuid.uuid5(UUID_NAMESPACE, name))


def fmt(value: float) -> str:
    return f"{value:.3f}".rstrip("0").rstrip(".")


def local_pad(ref: str, pin: int) -> tuple[float, float]:
    row = (pin - 1) // 2
    x = (0.0 if pin % 2 else -PITCH_MM) if ref == "J1" else (0.0 if pin % 2 else PITCH_MM)
    return x, row * PITCH_MM


def global_pad(ref: str, pin: int) -> tuple[float, float]:
    lx, ly = local_pad(ref, pin)
    ox, oy = J1_ORIGIN_MM if ref == "J1" else J2_ORIGIN_MM
    angle = 0.0 if ref == "J1" else J2_FOOTPRINT_ROTATION_DEG
    radians = math.radians(angle)
    # KiCad board coordinates are Y-down, so positive footprint rotation uses
    # the inverse sign of the conventional Cartesian XY matrix.
    return (
        ox + math.cos(radians) * lx + math.sin(radians) * ly,
        oy - math.sin(radians) * lx + math.cos(radians) * ly,
    )


def net_for(ref: str, pin: int) -> str | None:
    if ref == "J2" and pin == 11:
        return None
    if ref == "J2" and pin == 12:
        return NET_BY_PIN[7]
    return NET_BY_PIN[pin]


def pad(ref: str, pin: int) -> str:
    x, y = local_pad(ref, pin)
    net = net_for(ref, pin)
    net_clause = "" if net is None else f' (net {NET_CODE[net]} "{net}")'
    shape = "rect" if pin == 1 else "circle"
    return f'''    (pad "{pin}" thru_hole {shape} (at {fmt(x)} {fmt(y)})
      (size 1.7 1.7) (drill 1) (layers "*.Cu" "*.Mask"){net_clause}
      (uuid {uid(f'{ref}-pad-{pin}')}))'''


def fp_line(ref: str, index: int, start: tuple[float, float], end: tuple[float, float],
            layer: str, width: float) -> str:
    return f'''    (fp_line (start {fmt(start[0])} {fmt(start[1])}) (end {fmt(end[0])} {fmt(end[1])})
      (stroke (width {fmt(width)}) (type solid)) (layer "{layer}")
      (uuid {uid(f'{ref}-line-{index}-{layer}')}))'''


def fp_rect(ref: str, index: int, start: tuple[float, float], end: tuple[float, float],
            layer: str, width: float) -> str:
    return f'''    (fp_rect (start {fmt(start[0])} {fmt(start[1])}) (end {fmt(end[0])} {fmt(end[1])})
      (stroke (width {fmt(width)}) (type solid)) (fill none) (layer "{layer}")
      (uuid {uid(f'{ref}-rect-{index}-{layer}')}))'''


def j1_footprint() -> str:
    outline = []
    # KiCad 10.0.5 standard socket-strip body, fabrication outline and courtyard.
    for layer, width, bounds in (
        ("B.SilkS", 0.12, (-3.87, -1.33, 1.33, 11.49)),
        ("B.Fab", 0.10, (-3.81, -1.27, 1.27, 11.43)),
        ("B.CrtYd", 0.05, (-4.31, -1.77, 1.77, 11.93)),
    ):
        x0, y0, x1, y1 = bounds
        outline.append(fp_rect("J1", len(outline), (x0, y0), (x1, y1), layer, width))
    pads = "\n".join(pad("J1", pin) for pin in range(1, 11))
    return f'''  (footprint "{J1_FOOTPRINT}"
    (layer "B.Cu")
    (uuid {uid('J1-footprint')})
    (at {fmt(J1_ORIGIN_MM[0])} {fmt(J1_ORIGIN_MM[1])})
    (descr "KiCad 10 standard 2x05 2.54 mm vertical through-hole socket")
    (tags "Through hole socket strip THT 2x05 2.54mm double row")
    (property "Reference" "J1" (at -3.8 13.7 0) (layer "B.SilkS")
      (uuid {uid('J1-reference')}) (effects (font (size 1 1) (thickness 0.15)) (justify mirror)))
    (property "Value" "COMPUTE BLADE" (at -1.27 12.93 0) (layer "B.Fab")
      (uuid {uid('J1-value')}) (effects (font (size 1 1) (thickness 0.15)) (justify mirror)))
    (attr through_hole)
{chr(10).join(outline)}
    (fp_text user "1" (at 2 -0.8 0) (layer "B.SilkS")
      (uuid {uid('J1-pin1-text')}) (effects (font (size 0.8 0.8) (thickness 0.14)) (justify mirror)))
{pads}
    (model "{J1_MODEL}" (offset (xyz 0 0 0)) (scale (xyz 1 1 1)) (rotate (xyz 0 0 0)))
  )'''


def j2_footprint() -> str:
    graphics = [
        fp_rect("J2", 0, (-1.77, -1.77), (13.09, 14.47), "F.CrtYd", 0.05),
        fp_rect("J2", 1, (3.93, -1.38), (6.69, 14.08), "F.SilkS", 0.12),
        fp_rect("J2", 2, (4.04, -1.27), (6.58, 13.97), "F.Fab", 0.10),
        fp_line("J2", 3, (-1.27, -1.27), (0.0, -1.27), "F.SilkS", 0.12),
        fp_line("J2", 4, (-1.27, -1.27), (-1.27, 0.0), "F.SilkS", 0.12),
    ]
    for row in range(6):
        y = row * PITCH_MM
        graphics.append(fp_rect("J2", 10 + row, (6.69, y - 0.43), (12.69, y + 0.43), "F.SilkS", 0.12))
        graphics.append(fp_rect("J2", 20 + row, (6.58, y - 0.32), (12.58, y + 0.32), "F.Fab", 0.10))
    pads = "\n".join(pad("J2", pin) for pin in range(1, 13))
    return f'''  (footprint "{J2_FOOTPRINT}"
    (layer "F.Cu")
    (uuid {uid('J2-footprint')})
    (at {fmt(J2_ORIGIN_MM[0])} {fmt(J2_ORIGIN_MM[1])} {fmt(J2_FOOTPRINT_ROTATION_DEG)})
    (descr "KiCad 10 standard 2x06 2.54 mm horizontal through-hole pin header, 6 mm mating pins")
    (tags "Through hole angled pin header THT 2x06 2.54mm double row")
    (property "Reference" "J2" (at -3 -1.41 0) (layer "F.SilkS")
      (uuid {uid('J2-reference')}) (effects (font (size 1 1) (thickness 0.15))))
    (property "Value" "DDA GPS/RTC RIGHT-ANGLE" (at 7 13.8 0) (layer "F.Fab")
      (uuid {uid('J2-value')}) (effects (font (size 1 1) (thickness 0.15))))
    (attr through_hole)
{chr(10).join(graphics)}
    (fp_text user "1" (at -2.7 0 0) (layer "F.SilkS")
      (uuid {uid('J2-pin1-text')}) (effects (font (size 0.8 0.8) (thickness 0.14))))
    (fp_text user "MATES -> +Y" (at 9 14 0) (layer "F.SilkS")
      (uuid {uid('J2-mating-direction')}) (effects (font (size 0.8 0.8) (thickness 0.13))))
{pads}
    (model "{J2_MODEL}" (offset (xyz 0 0 0)) (scale (xyz 1 1 1)) (rotate (xyz 0 0 0)))
  )'''


def segment(start: tuple[float, float], end: tuple[float, float], layer: str,
            net: str, key: str) -> str:
    width = POWER_TRACE_WIDTH_MM if net in POWER_NETS else SIGNAL_TRACE_WIDTH_MM
    return (
        f'  (segment (start {fmt(start[0])} {fmt(start[1])}) '
        f'(end {fmt(end[0])} {fmt(end[1])}) (width {fmt(width)}) '
        f'(layer "{layer}") (net {NET_CODE[net]}) (uuid {uid(key)}))'
    )


def distance_to_segment(point: tuple[float, float], start: tuple[float, float],
                        end: tuple[float, float]) -> float:
    vx, vy = end[0] - start[0], end[1] - start[1]
    length2 = vx * vx + vy * vy
    if length2 == 0:
        return math.dist(point, start)
    t = max(0.0, min(1.0, ((point[0] - start[0]) * vx + (point[1] - start[1]) * vy) / length2))
    return math.dist(point, (start[0] + t * vx, start[1] + t * vy))


def simplify(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    result = []
    for point in points:
        if result and math.dist(result[-1], point) < 1e-6:
            continue
        result.append(point)
        while len(result) >= 3:
            a, b, c = result[-3:]
            cross = (b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0])
            # Collapse only forward collinear points.  A pad escape followed
            # by a grid path that briefly doubles back is intentional; using
            # the cross product alone deleted that escape and let the first
            # trace segment graze the neighboring connector pad.
            dot = (b[0] - a[0]) * (c[0] - b[0]) + (b[1] - a[1]) * (c[1] - b[1])
            if abs(cross) > 1e-8 or dot <= 0:
                break
            result.pop(-2)
    return result


def pad_escape(ref: str, pin: int) -> tuple[float, float]:
    """Give every THT pad a straight 1.5 mm exit away from its paired pad."""
    x, y = global_pad(ref, pin)
    if ref == "J1":
        return x + (1.5 if pin % 2 else -1.5), y
    return x, y + (-1.5 if pin % 2 else 1.5)


def routed_points(start: tuple[float, float], start_escape: tuple[float, float],
                  end_escape: tuple[float, float], end: tuple[float, float], layer: str,
                  net: str, completed: list[tuple[str, str, float, list[tuple[float, float]]]]) -> list[tuple[float, float]]:
    """Deterministically find a clearance-aware 0.1 mm grid route."""
    bounds = BOARD_BOUNDS_RELATIVE_J1_MM
    xmin = J1_ORIGIN_MM[0] + bounds[0] + 0.5
    xmax = J1_ORIGIN_MM[0] + bounds[1] - 0.5
    ymin = J1_ORIGIN_MM[1] + bounds[2] + 0.5
    ymax = J1_ORIGIN_MM[1] + bounds[3] - 0.5
    step = 0.1
    width = POWER_TRACE_WIDTH_MM if net in POWER_NETS else SIGNAL_TRACE_WIDTH_MM
    start_cell = (round((start_escape[0] - xmin) / step), round((start_escape[1] - ymin) / step))
    end_cell = (round((end_escape[0] - xmin) / step), round((end_escape[1] - ymin) / step))
    pad_centers = [
        (global_pad(ref, pin), net_for(ref, pin))
        for ref, count in (("J1", 10), ("J2", 12))
        for pin in range(1, count + 1)
    ]

    def position(cell: tuple[int, int]) -> tuple[float, float]:
        return xmin + cell[0] * step, ymin + cell[1] * step

    @lru_cache(maxsize=None)
    def blocked(cell: tuple[int, int]) -> bool:
        point = position(cell)
        if point[0] < xmin or point[0] > xmax or point[1] < ymin or point[1] > ymax:
            return True
        if cell in (start_cell, end_cell):
            return False
        pad_radius = 0.85 + width / 2 + 0.22
        for center, pad_net in pad_centers:
            if pad_net != net and math.dist(point, center) < pad_radius:
                return True
        for track_layer, track_net, track_width, points in completed:
            if track_layer != layer or track_net == net:
                continue
            clearance = (width + track_width) / 2 + 0.22
            if any(
                distance_to_segment(point, points[index], points[index + 1]) < clearance
                for index in range(len(points) - 1)
            ):
                return True
        return False

    queue = [(0.0, 0.0, start_cell)]
    previous: dict[tuple[int, int], tuple[int, int] | None] = {start_cell: None}
    cost = {start_cell: 0.0}
    directions = ((1, 0), (0, -1), (-1, 0), (0, 1), (1, -1), (-1, -1), (-1, 1), (1, 1))
    while queue:
        _estimate, current_cost, current = heapq.heappop(queue)
        if current == end_cell:
            break
        if current_cost != cost.get(current):
            continue
        for dx, dy in directions:
            neighbor = current[0] + dx, current[1] + dy
            if blocked(neighbor):
                continue
            move = math.sqrt(2.0) if dx and dy else 1.0
            candidate = current_cost + move
            if candidate >= cost.get(neighbor, float("inf")):
                continue
            cost[neighbor] = candidate
            previous[neighbor] = current
            heuristic = math.hypot(end_cell[0] - neighbor[0], end_cell[1] - neighbor[1])
            heapq.heappush(queue, (candidate + heuristic, candidate, neighbor))
    if end_cell not in previous:
        raise RuntimeError(f"could not route {net} on {layer} with configured clearances")
    cells = []
    current: tuple[int, int] | None = end_cell
    while current is not None:
        cells.append(current)
        current = previous[current]
    points = [start, start_escape, *(position(cell) for cell in reversed(cells)), end_escape, end]
    return simplify(points)


def build_board() -> str:
    bounds = BOARD_BOUNDS_RELATIVE_J1_MM
    board_left, board_right = J1_ORIGIN_MM[0] + bounds[0], J1_ORIGIN_MM[0] + bounds[1]
    board_top, board_bottom = J1_ORIGIN_MM[1] + bounds[2], J1_ORIGIN_MM[1] + bounds[3]
    nets = ['  (net 0 "")'] + [f'  (net {code} "{net}")' for net, code in NET_CODE.items()]
    completed: list[tuple[str, str, float, list[tuple[float, float]]]] = []
    routes = []
    # Alternating outer/inner order leaves routing channels for the remaining
    # nets. Odd pins use F.Cu and even pins use B.Cu.
    for pin in ROUTE_ORDER:
        net = NET_BY_PIN[pin]
        layer = "F.Cu" if pin % 2 else "B.Cu"
        points = routed_points(
            global_pad("J1", pin), pad_escape("J1", pin),
            pad_escape("J2", pin), global_pad("J2", pin), layer, net, completed,
        )
        width = POWER_TRACE_WIDTH_MM if net in POWER_NETS else SIGNAL_TRACE_WIDTH_MM
        completed.append((layer, net, width, points))
        routes.extend(
            segment(points[index], points[index + 1], layer, net, f"route-{pin}-{index}")
            for index in range(len(points) - 1)
        )

    # Route physical pin 2 after all other bottom-layer nets.  Its 0.5 mm
    # trace uses the otherwise empty bottom perimeter, keeping both bends far
    # from the adjacent 3V3 pin-1 pads without consuming an A* routing channel.
    pin2_net = NET_BY_PIN[2]
    pin2_points = [
        global_pad("J1", 2),
        (91.00, 60.16),
        (91.00, 73.80),
        (124.50, 73.80),
        (124.50, 63.70),
        pad_escape("J2", 2),
        global_pad("J2", 2),
    ]
    completed.append(("B.Cu", pin2_net, POWER_TRACE_WIDTH_MM, pin2_points))
    routes.extend(
        segment(pin2_points[index], pin2_points[index + 1], "B.Cu", pin2_net, f"route-2-{index}")
        for index in range(len(pin2_points) - 1)
    )

    pps_net = NET_BY_PIN[7]
    branch = routed_points(
        global_pad("J2", 12), pad_escape("J2", 12),
        pad_escape("J1", 7), global_pad("J1", 7), "F.Cu", pps_net, completed,
    )
    completed.append(("F.Cu", pps_net, SIGNAL_TRACE_WIDTH_MM, branch))
    routes.extend(
        segment(branch[index], branch[index + 1], "F.Cu", pps_net, f"pps-branch-{index}")
        for index in range(len(branch) - 1)
    )

    return f'''(kicad_pcb (version 20240108) (generator pcbnew)
  (general (thickness {fmt(BOARD_THICKNESS_MM)}))
  (paper "A4")
  (layers
    (0 "F.Cu" signal) (31 "B.Cu" signal)
    (36 "B.SilkS" user "b.silkscreen") (37 "F.SilkS" user "f.silkscreen")
    (38 "B.Mask" user) (39 "F.Mask" user) (44 "Edge.Cuts" user)
    (46 "B.CrtYd" user "b.courtyard") (47 "F.CrtYd" user "f.courtyard")
    (48 "B.Fab" user) (49 "F.Fab" user))
  (setup
    (stackup
      (layer "F.SilkS" (type "Top Silk Screen")) (layer "F.Mask" (type "Top Solder Mask"))
      (layer "F.Cu" (type "copper") (thickness 0.035))
      (layer "dielectric 1" (type "core") (thickness 0.73) (material "FR4") (epsilon_r 4.5) (loss_tangent 0.02))
      (layer "B.Cu" (type "copper") (thickness 0.035))
      (layer "B.Mask" (type "Bottom Solder Mask")) (layer "B.SilkS" (type "Bottom Silk Screen"))
      (copper_finish "None") (dielectric_constraints no))
    (pad_to_mask_clearance 0) (allow_soldermask_bridges_in_footprints no))
{chr(10).join(nets)}
{j1_footprint()}
{j2_footprint()}
  (gr_rect (start {fmt(board_left)} {fmt(board_top)}) (end {fmt(board_right)} {fmt(board_bottom)})
    (stroke (width 0.1) (type default)) (fill none) (layer "Edge.Cuts") (uuid {uid('board-outline')}))
  (gr_text "DDA GPS/RTC" (at 107 73.9 0) (layer "F.SilkS") (uuid {uid('front-label-dda')})
    (effects (font (size 0.8 0.8) (thickness 0.13))))
  (gr_text "PPS -> GPIO4" (at 102.8 58.75 0) (layer "F.SilkS") (uuid {uid('front-label-pps')})
    (effects (font (size 0.8 0.8) (thickness 0.13))))
  (gr_text "COMPUTE BLADE" (at 102.2 73.9 0) (layer "B.SilkS") (uuid {uid('bottom-label-compute')})
    (effects (font (size 0.8 0.8) (thickness 0.13)) (justify mirror)))
{chr(10).join(routes)}
)\n'''


def build_report() -> str:
    lines = ["Compute Blade to DDA GPS/RTC adapter connectivity", "Physical header pin numbers only", "", "Pin     Net", "------- ---------------------------"]
    for pin in range(1, 11):
        lines.append(f"J1.{pin:<3} {net_for('J1', pin)}")
    for pin in range(1, 13):
        lines.append(f"J2.{pin:<3} {net_for('J2', pin) or 'NC'}")
    return "\n".join(lines) + "\n"


def main() -> None:
    BOARD_PATH.parent.mkdir(parents=True, exist_ok=True)
    BOARD_PATH.write_text(build_board(), encoding="utf-8")
    REPORT_PATH.write_text(build_report(), encoding="utf-8")
    print(f"Wrote {BOARD_PATH.relative_to(ROOT)}")
    print(f"Wrote {REPORT_PATH.relative_to(ROOT)}")
    print(f"J1/J2 centerline offset: {J2_CENTERLINE_OFFSET_MM:.1f} mm")
    print(f"J2 right-angle mating direction: +Y (top/interior side); KiCad footprint rotation: {J2_FOOTPRINT_ROTATION_DEG:g} degrees")


if __name__ == "__main__":
    main()
