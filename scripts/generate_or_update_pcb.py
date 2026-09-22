#!/usr/bin/env python3
"""Deterministically generate the routed two-connector KiCad PCB."""

from __future__ import annotations

import uuid
import math
import heapq
from pathlib import Path

from design_config import (
    BOARD_THICKNESS_MM,
    BOARD_BOUNDS_RELATIVE_J1_MM,
    ROUTING_BOUNDS_RELATIVE_J1_MM,
    J1_FOOTPRINT,
    J1_MODEL,
    J1_ORIGIN_MM,
    J1_CANDIDATE_PART,
    J2_FOOTPRINT,
    J2_FOOTPRINT_ROTATION_DEG,
    J2_MODEL,
    J2_ORIGIN_MM,
    J2_CANDIDATE_PART,
    J2_CENTERLINE_OFFSET_MM,
    PITCH_MM,
    POWER_TRACE_WIDTH_MM,
    SIGNAL_TRACE_WIDTH_MM,
)


ROOT = Path(__file__).resolve().parents[1]
BOARD_PATH = ROOT / "pcb" / "compute-blade-dda-adapter.kicad_pcb"
REPORT_PATH = ROOT / "CONNECTIVITY.txt"
BOM_PATH = ROOT / "BOM.csv"
UUID_NAMESPACE = uuid.UUID("5ec70a29-b9c1-44f3-96f8-6bd81180ce3d")

NET_BY_PIN = {
    1: "3V3", 2: "5V_PIN2", 3: "SDA_GPIO2", 4: "5V_PIN4",
    5: "SCL_GPIO3", 6: "GND_PIN6", 7: "PPS_GPIO4",
    8: "UART_TX_TO_GPS_RX", 9: "GND_PIN9", 10: "UART_RX_FROM_GPS_TX",
}
NET_CODE = {net: index for index, net in enumerate(NET_BY_PIN.values(), start=1)}
POWER_NETS = {"3V3", "5V_PIN2", "5V_PIN4", "GND_PIN6", "GND_PIN9"}
ROUTE_ORDER = (1, 2, 5, 8, 3, 4, 6, 7, 9, 10)


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
      (size 1.8 1.8) (drill 1) (layers "*.Cu" "*.Mask"){net_clause}
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
    # Samtec HLE five-position double-row body and courtyard.
    for layer, width, bounds in (
        ("F.SilkS", 0.12, (-3.87, -1.33, 1.33, 11.49)),
        ("F.Fab", 0.10, (-3.81, -1.27, 1.27, 11.43)),
        ("F.CrtYd", 0.05, (-4.31, -1.77, 1.77, 11.93)),
    ):
        x0, y0, x1, y1 = bounds
        outline.append(fp_rect("J1", len(outline), (x0, y0), (x1, y1), layer, width))
    pads = "\n".join(pad("J1", pin) for pin in range(1, 11))
    return f'''  (footprint "{J1_FOOTPRINT}"
    (layer "F.Cu")
    (uuid {uid('J1-footprint')})
    (at {fmt(J1_ORIGIN_MM[0])} {fmt(J1_ORIGIN_MM[1])})
    (descr "Samtec HLE-105-02-L-DV-PE-BE 2x5 bottom-entry pass-through socket")
    (tags "Samtec HLE bottom entry pass through 2x5 2.54mm")
    (property "Reference" "J1" (at -1.27 13.0 0) (layer "F.SilkS")
      (uuid {uid('J1-reference')}) (effects (font (size 1 1) (thickness 0.15))))
    (property "Value" "HLE-105-02-L-DV-PE-BE" (at -1.27 13.0 0) (layer "F.Fab")
      (uuid {uid('J1-value')}) (effects (font (size 1 1) (thickness 0.15))))
    (attr through_hole)
{chr(10).join(outline)}
    (fp_text user "1" (at 2 -0.8 0) (layer "F.SilkS")
      (uuid {uid('J1-pin1-text')}) (effects (font (size 0.8 0.8) (thickness 0.14))))
{pads}
    (model "{J1_MODEL}" (offset (xyz 0 0 0)) (scale (xyz 1 1 1)) (rotate (xyz 0 0 0)))
  )'''


def j2_footprint() -> str:
    graphics = [
        fp_rect("J2", 0, (-1.745, -1.77), (4.285, 14.47), "B.CrtYd", 0.05),
        fp_rect("J2", 1, (-1.305, -1.33), (3.845, 14.03), "B.SilkS", 0.12),
        fp_rect("J2", 2, (-1.245, -1.27), (3.785, 13.97), "B.Fab", 0.10),
        fp_line("J2", 3, (-1.245, -1.27), (0.0, -1.27), "B.SilkS", 0.12),
        fp_line("J2", 4, (-1.245, -1.27), (-1.245, 0.0), "B.SilkS", 0.12),
    ]
    pads = "\n".join(pad("J2", pin) for pin in range(1, 13))
    return f'''  (footprint "{J2_FOOTPRINT}"
    (layer "B.Cu")
    (uuid {uid('J2-footprint')})
    (at {fmt(J2_ORIGIN_MM[0])} {fmt(J2_ORIGIN_MM[1])} {fmt(J2_FOOTPRINT_ROTATION_DEG)})
    (descr "Samtec MTLW-106-06-G-D-035 reverse-mounted pass-through 2x6 header")
    (tags "Samtec MTLW reverse pass through 2x6 2.54mm")
    (property "Reference" "J2" (at 1.27 15.2 0) (layer "B.SilkS")
      (uuid {uid('J2-reference')}) (effects (font (size 1 1) (thickness 0.15)) (justify mirror)))
    (property "Value" "MTLW-106-06-G-D-035 REVERSE" (at 1.27 15.2 0) (layer "B.Fab")
      (uuid {uid('J2-value')}) (effects (font (size 1 1) (thickness 0.15)) (justify mirror)))
    (attr through_hole)
{chr(10).join(graphics)}
    (fp_text user "1" (at -2.4 0 0) (layer "B.SilkS")
      (uuid {uid('J2-pin1-text')}) (effects (font (size 0.8 0.8) (thickness 0.14)) (justify mirror)))
    (fp_text user "REVERSE / DDA ABOVE" (at 1.27 6.35 90) (layer "B.SilkS")
      (uuid {uid('J2-mating-direction')}) (effects (font (size 0.65 0.65) (thickness 0.11)) (justify mirror)))
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


def distance_between_segments(
    a: tuple[float, float], b: tuple[float, float],
    c: tuple[float, float], d: tuple[float, float],
) -> float:
    """Return the exact minimum distance between two closed 2-D segments."""
    def orientation(p, q, r):
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])

    def on_segment(p, q, r):
        return (
            min(p[0], r[0]) - 1e-9 <= q[0] <= max(p[0], r[0]) + 1e-9
            and min(p[1], r[1]) - 1e-9 <= q[1] <= max(p[1], r[1]) + 1e-9
        )

    ab_c, ab_d = orientation(a, b, c), orientation(a, b, d)
    cd_a, cd_b = orientation(c, d, a), orientation(c, d, b)
    if ab_c * ab_d < 0 and cd_a * cd_b < 0:
        return 0.0
    if (
        (abs(ab_c) <= 1e-9 and on_segment(a, c, b))
        or (abs(ab_d) <= 1e-9 and on_segment(a, d, b))
        or (abs(cd_a) <= 1e-9 and on_segment(c, a, d))
        or (abs(cd_b) <= 1e-9 and on_segment(c, b, d))
    ):
        return 0.0
    return min(
        distance_to_segment(a, c, d), distance_to_segment(b, c, d),
        distance_to_segment(c, a, b), distance_to_segment(d, a, b),
    )


def segment_intersects_aabb(
    start: tuple[float, float], end: tuple[float, float],
    xmin: float, xmax: float, ymin: float, ymax: float,
) -> bool:
    """Liang-Barsky test for a segment intersecting a closed rectangle."""
    dx, dy = end[0] - start[0], end[1] - start[1]
    lower, upper = 0.0, 1.0
    for p, q in (
        (-dx, start[0] - xmin), (dx, xmax - start[0]),
        (-dy, start[1] - ymin), (dy, ymax - start[1]),
    ):
        if abs(p) <= 1e-12:
            if q < 0:
                return False
            continue
        ratio = q / p
        if p < 0:
            lower = max(lower, ratio)
        else:
            upper = min(upper, ratio)
        if lower > upper:
            return False
    return True


def segment_violates_pad_clearance(
    start: tuple[float, float], end: tuple[float, float],
    center: tuple[float, float], pin: int, track_width: float,
) -> bool:
    clearance = track_width / 2 + 0.15
    if pin == 1:
        # Pin 1 is a 1.8 mm square pad; treating it as a 0.9 mm-radius circle
        # misses copper near its corners.
        half_extent = 0.90 + clearance
        return segment_intersects_aabb(
            start, end,
            center[0] - half_extent, center[0] + half_extent,
            center[1] - half_extent, center[1] + half_extent,
        )
    return distance_to_segment(center, start, end) < 0.90 + clearance


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
    return x, y + (1.5 if pin % 2 else -1.5)


def routed_points(start: tuple[float, float], start_escape: tuple[float, float],
                  end_escape: tuple[float, float], end: tuple[float, float], layer: str,
                  net: str, completed: list[tuple[str, str, float, list[tuple[float, float]]]]) -> list[tuple[float, float]]:
    """Deterministically find a clearance-aware 0.1 mm grid route."""
    bounds = ROUTING_BOUNDS_RELATIVE_J1_MM
    xmin = J1_ORIGIN_MM[0] + bounds[0] + 0.5
    xmax = J1_ORIGIN_MM[0] + bounds[1] - 0.5
    ymin = J1_ORIGIN_MM[1] + bounds[2] + 0.5
    ymax = J1_ORIGIN_MM[1] + bounds[3] - 0.5
    step = 0.25
    width = POWER_TRACE_WIDTH_MM if net in POWER_NETS else SIGNAL_TRACE_WIDTH_MM
    start_cell = (round((start_escape[0] - xmin) / step), round((start_escape[1] - ymin) / step))
    end_cell = (round((end_escape[0] - xmin) / step), round((end_escape[1] - ymin) / step))
    pad_centers = [
        (global_pad(ref, pin), net_for(ref, pin), pin)
        for ref, count in (("J1", 10), ("J2", 12))
        for pin in range(1, count + 1)
    ]

    def position(cell: tuple[int, int]) -> tuple[float, float]:
        return xmin + cell[0] * step, ymin + cell[1] * step

    def segment_blocked(a: tuple[float, float], b: tuple[float, float]) -> bool:
        if any(point[0] < xmin or point[0] > xmax or point[1] < ymin or point[1] > ymax for point in (a, b)):
            return True
        for center, pad_net, pin in pad_centers:
            if pad_net != net and segment_violates_pad_clearance(a, b, center, pin, width):
                return True
        for track_layer, track_net, track_width, points in completed:
            if track_layer != layer or track_net == net:
                continue
            clearance = (width + track_width) / 2 + 0.15
            probes = (a, ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2), b)
            if any(
                distance_to_segment(probe, points[index], points[index + 1]) < clearance
                for probe in probes
                for index in range(len(points) - 1)
            ):
                return True
        return False

    # The two pad-escape segments are not A* edges, so validate them explicitly.
    if segment_blocked(start, start_escape) or segment_blocked(end_escape, end):
        raise RuntimeError(f"pad escape for {net} on {layer} violates clearance")

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
            if segment_blocked(position(current), position(neighbor)):
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


def via_clear(
    point: tuple[float, float], net: str,
    completed: list[tuple[str, str, float, list[tuple[float, float]]]],
) -> bool:
    for ref, count in (("J1", 10), ("J2", 12)):
        for pin in range(1, count + 1):
            if net_for(ref, pin) != net and math.dist(point, global_pad(ref, pin)) < 1.15:
                return False
    for _layer, track_net, width, points in completed:
        if track_net == net:
            continue
        clearance = 0.4 + width / 2 + 0.15
        if any(distance_to_segment(point, points[i], points[i + 1]) < clearance for i in range(len(points) - 1)):
            return False
    return True


def route_connection(
    start: tuple[float, float], start_escape: tuple[float, float],
    end_escape: tuple[float, float], end: tuple[float, float],
    preferred: str, net: str,
    completed: list[tuple[str, str, float, list[tuple[float, float]]]],
) -> tuple[
    list[tuple[str, list[tuple[float, float]]]],
    tuple[float, float] | tuple[tuple[float, float], tuple[float, float]] | None,
]:
    other = "B.Cu" if preferred == "F.Cu" else "F.Cu"
    for layer in (preferred, other):
        try:
            return [(layer, routed_points(start, start_escape, end_escape, end, layer, net, completed))], None
        except RuntimeError:
            pass
    # A single plated through via is sufficient for the only topological
    # crossings created by rotating the destination connector 90 degrees.
    for first, second in ((preferred, other), (other, preferred)):
        for x in (104.0, 108.0, 112.0, 116.0, 120.0, 124.0):
            for y in (51.0, 54.0, 57.0, 60.0, 63.0, 66.0, 69.0, 72.0, 75.0, 78.0):
                via = (x, y)
                if not via_clear(via, net, completed):
                    continue
                try:
                    first_points = routed_points(
                        start, start_escape, via, via, first, net, completed
                    )
                    second_points = routed_points(
                        via, via, end_escape, end, second, net, completed
                    )
                    return [(first, first_points), (second, second_points)], via
                except RuntimeError:
                    continue
    # Final deterministic fallback: two vias put the long middle span on the
    # opposite layer while keeping both connector escapes on their preferred
    # layer. This handles the 90-degree fan-out without adding more layers.
    for outer, middle in ((preferred, other), (other, preferred)):
        for y1 in (51.0, 55.0, 59.0, 63.0, 67.0, 71.0, 75.0, 79.0):
            via1 = (106.0, y1)
            if not via_clear(via1, net, completed):
                continue
            for y2 in (51.0, 55.0, 59.0, 63.0, 67.0, 71.0, 75.0, 79.0):
                via2 = (122.0, y2)
                if not via_clear(via2, net, completed):
                    continue
                try:
                    first_points = routed_points(start, start_escape, via1, via1, outer, net, completed)
                    middle_points = routed_points(via1, via1, via2, via2, middle, net, completed)
                    last_points = routed_points(via2, via2, end_escape, end, outer, net, completed)
                    return [
                        (outer, first_points), (middle, middle_points), (outer, last_points)
                    ], (via1, via2)
                except RuntimeError:
                    continue
    raise RuntimeError(f"could not route {net} with up to two vias")


def via(point: tuple[float, float], net: str, key: str) -> str:
    return (
        f'  (via (at {fmt(point[0])} {fmt(point[1])}) (size 0.8) (drill 0.4) '
        f'(layers "F.Cu" "B.Cu") (net {NET_CODE[net]}) (uuid {uid(key)}))'
    )


def assert_route_clearances(
    completed: list[tuple[str, str, float, list[tuple[float, float]]]],
) -> None:
    """Independently audit every finished copper segment before serialization."""
    segments = [
        (layer, net, width, points[index], points[index + 1])
        for layer, net, width, points in completed
        for index in range(len(points) - 1)
    ]
    for layer, net, width, start, end in segments:
        for ref, count in (("J1", 10), ("J2", 12)):
            for pin in range(1, count + 1):
                if net_for(ref, pin) == net:
                    continue
                center = global_pad(ref, pin)
                if segment_violates_pad_clearance(start, end, center, pin, width):
                    raise RuntimeError(
                        f"{net} {layer} segment {start}->{end} violates copper clearance "
                        f"to {ref}.{pin} at {center}"
                    )
    for index, (layer, net, width, start, end) in enumerate(segments):
        for other_layer, other_net, other_width, other_start, other_end in segments[index + 1:]:
            if layer != other_layer or net == other_net:
                continue
            required = (width + other_width) / 2 + 0.15
            actual = distance_between_segments(start, end, other_start, other_end)
            if actual < required - 1e-6:
                raise RuntimeError(
                    f"{net}/{other_net} segments on {layer} have only {actual:.4f} mm "
                    f"centerline clearance; {required:.4f} mm required"
                )


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
        preferred = "F.Cu" if pin % 2 else "B.Cu"
        pieces, via_point = route_connection(
            global_pad("J1", pin), pad_escape("J1", pin),
            pad_escape("J2", pin), global_pad("J2", pin), preferred, net, completed,
        )
        width = POWER_TRACE_WIDTH_MM if net in POWER_NETS else SIGNAL_TRACE_WIDTH_MM
        for piece_index, (layer, points) in enumerate(pieces):
            completed.append((layer, net, width, points))
            routes.extend(
                segment(points[index], points[index + 1], layer, net, f"route-{pin}-{piece_index}-{index}")
                for index in range(len(points) - 1)
            )
        if via_point is not None:
            via_points = via_point if isinstance(via_point[0], tuple) else (via_point,)
            for via_index, point in enumerate(via_points):
                routes.append(via(point, net, f"route-{pin}-via-{via_index}"))

    pps_net = NET_BY_PIN[7]
    branch_pieces, branch_via = route_connection(
        global_pad("J2", 12), pad_escape("J2", 12),
        pad_escape("J2", 7), global_pad("J2", 7), "F.Cu", pps_net, completed,
    )
    for piece_index, (layer, branch) in enumerate(branch_pieces):
        completed.append((layer, pps_net, SIGNAL_TRACE_WIDTH_MM, branch))
        routes.extend(
            segment(branch[index], branch[index + 1], layer, pps_net, f"pps-branch-{piece_index}-{index}")
            for index in range(len(branch) - 1)
        )
    if branch_via is not None:
        via_points = branch_via if isinstance(branch_via[0], tuple) else (branch_via,)
        for via_index, point in enumerate(via_points):
            routes.append(via(point, pps_net, f"pps-branch-via-{via_index}"))

    assert_route_clearances(completed)

    physical_xmin = J1_ORIGIN_MM[0] + bounds[0]
    physical_xmax = J1_ORIGIN_MM[0] + bounds[1]
    physical_ymin = J1_ORIGIN_MM[1] + bounds[2]
    physical_ymax = J1_ORIGIN_MM[1] + bounds[3]
    for _layer, net, width, points in completed:
        edge = width / 2
        for x, y in points:
            if not (
                physical_xmin + edge <= x <= physical_xmax - edge
                and physical_ymin + edge <= y <= physical_ymax - edge
            ):
                raise RuntimeError(f"route {net} leaves the physical board outline at {(x, y)}")

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
      (layer "dielectric 1" (type "core") (thickness 0.53) (material "FR4") (epsilon_r 4.5) (loss_tangent 0.02))
      (layer "B.Cu" (type "copper") (thickness 0.035))
      (layer "B.Mask" (type "Bottom Solder Mask")) (layer "B.SilkS" (type "Bottom Silk Screen"))
      (copper_finish "None") (dielectric_constraints no))
    (pad_to_mask_clearance 0) (allow_soldermask_bridges_in_footprints no))
{chr(10).join(nets)}
{j1_footprint()}
{j2_footprint()}
  (gr_rect (start {fmt(board_left)} {fmt(board_top)}) (end {fmt(board_right)} {fmt(board_bottom)})
    (stroke (width 0.1) (type default)) (fill none) (layer "Edge.Cuts") (uuid {uid('board-outline')}))
  (gr_text "DDA GPS/RTC" (at 126 71.6 0) (layer "F.SilkS") (uuid {uid('front-label-dda')})
    (effects (font (size 0.8 0.8) (thickness 0.13))))
  (gr_text "PPS -> GPIO4" (at 111 58.4 0) (layer "F.SilkS") (uuid {uid('front-label-pps')})
    (effects (font (size 0.8 0.8) (thickness 0.13))))
  (gr_text "COMPUTE BLADE" (at 107 71.6 0) (layer "B.SilkS") (uuid {uid('bottom-label-compute')})
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


def build_bom() -> str:
    return (
        "Reference,Quantity,Manufacturer,Manufacturer Part Number,Description,Mounting\n"
        f'J1,1,Samtec,"{J1_CANDIDATE_PART.removeprefix("Samtec ")}",'
        '2x5 2.54 mm bottom-entry pass-through receptacle,Top / through-hole\n'
        f'J2,1,Samtec,"{J2_CANDIDATE_PART.removeprefix("Samtec ")}",'
        '2x6 2.54 mm variable-post header used in reverse,Bottom / through-hole\n'
    )


def main() -> None:
    BOARD_PATH.parent.mkdir(parents=True, exist_ok=True)
    BOARD_PATH.write_text(build_board(), encoding="utf-8")
    REPORT_PATH.write_text(build_report(), encoding="utf-8")
    BOM_PATH.write_text(build_bom(), encoding="utf-8")
    print(f"Wrote {BOARD_PATH.relative_to(ROOT)}")
    print(f"Wrote {REPORT_PATH.relative_to(ROOT)}")
    print(f"Wrote {BOM_PATH.relative_to(ROOT)}")
    print(f"J1-to-J2 pin-1 X offset: {J2_CENTERLINE_OFFSET_MM:.3f} mm")
    print(f"J2 reverse vertical mating direction: +Z; KiCad footprint rotation: {J2_FOOTPRINT_ROTATION_DEG:g} degrees")


if __name__ == "__main__":
    main()
