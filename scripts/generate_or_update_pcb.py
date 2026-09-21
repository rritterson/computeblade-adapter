#!/usr/bin/env python3
"""Deterministically generate the routed two-connector KiCad PCB."""

from __future__ import annotations

import uuid
import math
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
    return (
        ox + math.cos(radians) * lx - math.sin(radians) * ly,
        oy + math.sin(radians) * lx + math.cos(radians) * ly,
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
    (fp_text user "MATES -> SSD" (at 9 14 0) (layer "F.SilkS")
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


def route_pair(pin: int) -> list[str]:
    net = NET_BY_PIN[pin]
    start = global_pad("J1", pin)
    end = global_pad("J2", pin)
    row = (pin - 1) // 2
    if pin % 2:
        # Monotonic front-layer L-routes; later columns turn farther right, so
        # the routes do not cross. Pin 7 is split at the PPS branch junction.
        points = [start]
        if pin == 7:
            points.append((116.35, start[1]))
        points.extend([(end[0], start[1]), end])
        layer = "F.Cu"
    else:
        # Even pins escape left, fan through ordered top lanes, and approach
        # their J2 pads from -Y. This avoids every through-hole odd-row pad.
        escape_x = J1_ORIGIN_MM[0] - 4.0 - row * 1.2
        lane_y = J1_ORIGIN_MM[1] - 6.0 - row * 1.2
        points = [start, (escape_x, start[1]), (escape_x, lane_y), (end[0], lane_y), end]
        layer = "B.Cu"
    return [
        segment(points[i], points[i + 1], layer, net, f"route-{pin}-{i}")
        for i in range(len(points) - 1)
        if points[i] != points[i + 1]
    ]


def build_board() -> str:
    bounds = BOARD_BOUNDS_RELATIVE_J1_MM
    board_left, board_right = J1_ORIGIN_MM[0] + bounds[0], J1_ORIGIN_MM[0] + bounds[1]
    board_top, board_bottom = J1_ORIGIN_MM[1] + bounds[2], J1_ORIGIN_MM[1] + bounds[3]
    nets = ['  (net 0 "")'] + [f'  (net {code} "{net}")' for net, code in NET_CODE.items()]
    routes = [route for pin in range(1, 11) for route in route_pair(pin)]

    p12 = global_pad("J2", 12)
    pps_join = (116.35, global_pad("J1", 7)[1])
    branch = [p12, (p12[0], board_top + 1.0), (pps_join[0], board_top + 1.0), pps_join]
    routes.extend(
        segment(branch[i], branch[i + 1], "F.Cu", NET_BY_PIN[7], f"pps-branch-{i}")
        for i in range(len(branch) - 1)
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
    print(f"J2 right-angle mating direction: -Y (SSD side); footprint rotation: {J2_FOOTPRINT_ROTATION_DEG:g} degrees")


if __name__ == "__main__":
    main()
