#!/usr/bin/env python3
"""Deterministically generate the routed two-connector KiCad PCB."""

from __future__ import annotations

import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BOARD_PATH = ROOT / "pcb" / "compute-blade-dda-adapter.kicad_pcb"
REPORT_PATH = ROOT / "CONNECTIVITY.txt"

# Change this one value to move J2 laterally relative to J1. The board outline,
# connector placement, labels, and routes are all derived from it.
CONNECTOR_OFFSET_MM = 10.0

PITCH_MM = 2.54
J1_ORIGIN = (100.0, 60.16)
J2_ORIGIN = (J1_ORIGIN[0] + CONNECTOR_OFFSET_MM, J1_ORIGIN[1])
TRACE_WIDTH_MM = 0.20
ROUTE_OFFSET_MM = 1.30
UUID_NAMESPACE = uuid.UUID("5ec70a29-b9c1-44f3-96f8-6bd81180ce3d")

NET_BY_PIN = {
    1: "3V3",
    2: "5V_PIN2",
    3: "SDA_GPIO2",
    4: "5V_PIN4",
    5: "SCL_GPIO3",
    6: "GND_PIN6",
    7: "PPS_GPIO4",
    8: "UART_TX_TO_GPS_RX",
    9: "GND_PIN9",
    10: "UART_RX_FROM_GPS_TX",
}
NET_CODE = {net: index for index, net in enumerate(NET_BY_PIN.values(), start=1)}


def uid(name: str) -> str:
    return str(uuid.uuid5(UUID_NAMESPACE, name))


def fmt(value: float) -> str:
    return f"{value:.3f}".rstrip("0").rstrip(".")


def local_pad(pin: int) -> tuple[float, float]:
    row = (pin - 1) // 2
    return (0.0 if pin % 2 else PITCH_MM, row * PITCH_MM)


def global_pad(ref: str, pin: int) -> tuple[float, float]:
    """Apply the 180-degree footprint rotation used by both connectors.

    KiCad stores bottom-footprint local pad coordinates without an additional
    board-space X mirror; the layer controls viewing/mating side separately.
    """
    lx, ly = local_pad(pin)
    ox, oy = J1_ORIGIN if ref == "J1" else J2_ORIGIN
    return ox - lx, oy - ly


def net_for(ref: str, pin: int) -> str | None:
    if ref == "J2" and pin == 11:
        return None
    if ref == "J2" and pin == 12:
        return NET_BY_PIN[7]
    return NET_BY_PIN[pin]


def footprint(ref: str, value: str, library_id: str, rows: int, side: str,
              origin: tuple[float, float]) -> str:
    silk = "B.SilkS" if side == "B.Cu" else "F.SilkS"
    fab = "B.Fab" if side == "B.Cu" else "F.Fab"
    justify = " (justify mirror)" if side == "B.Cu" else ""
    max_y = (rows - 1) * PITCH_MM
    ref_y = max_y / 2
    value_y = rows * PITCH_MM + 0.7
    pads = []
    for pin in range(1, rows * 2 + 1):
        px, py = local_pad(pin)
        net = net_for(ref, pin)
        net_clause = "" if net is None else f' (net {NET_CODE[net]} "{net}")'
        shape = "rect" if pin == 1 else "oval"
        pads.append(
            f'''    (pad "{pin}" thru_hole {shape} (at {fmt(px)} {fmt(py)} 180)
      (size 1.7 1.7) (drill 1) (layers "*.Cu" "*.Mask"){net_clause}
      (uuid {uid(f'{ref}-pad-{pin}')}))'''
        )

    # Marker is outside pin 1 on the outboard side for each transformed footprint.
    marker_x = -1.9
    return f'''  (footprint "{library_id}"
    (layer "{side}")
    (uuid {uid(ref + '-footprint')})
    (at {fmt(origin[0])} {fmt(origin[1])} 180)
    (descr "Standard 2x{rows:02d} 2.54 mm vertical {'socket' if ref == 'J1' else 'pin header'}")
    (tags "Through hole {'socket' if ref == 'J1' else 'pin header'} 2x{rows:02d} 2.54mm")
    (property "Reference" "{ref}"
      (at -2.5 {fmt(ref_y)} 90)
      (layer "{silk}")
      (uuid {uid(ref + '-reference')})
      (effects (font (size 1 1) (thickness 0.15)){justify}))
    (property "Value" "{value}"
      (at 1.27 {fmt(value_y)} 0)
      (layer "{fab}")
      (uuid {uid(ref + '-value')})
      (effects (font (size 1 1) (thickness 0.15)){justify}))
    (attr through_hole)
    (fp_rect (start -1.27 -1.27) (end 3.81 {fmt(max_y + 1.27)})
      (stroke (width 0.2) (type default)) (fill none) (layer "{silk}")
      (uuid {uid(ref + '-silk-outline')}))
    (fp_rect (start -1.27 -1.27) (end 3.81 {fmt(max_y + 1.27)})
      (stroke (width 0.1) (type default)) (fill none) (layer "{fab}")
      (uuid {uid(ref + '-fab-outline')}))
    (fp_circle (center {fmt(marker_x)} 0) (end {fmt(marker_x + 0.45)} 0)
      (stroke (width 0.25) (type default)) (fill none) (layer "{silk}")
      (uuid {uid(ref + '-pin1-circle')}))
    (fp_text user "1" (at {fmt(marker_x)} -1.05 0) (layer "{silk}")
      (uuid {uid(ref + '-pin1-text')})
      (effects (font (size 0.8 0.8) (thickness 0.14)){justify}))
{chr(10).join(pads)}
  )'''


def segment(start: tuple[float, float], end: tuple[float, float], layer: str,
            net: str, key: str) -> str:
    return (
        f'  (segment (start {fmt(start[0])} {fmt(start[1])}) '
        f'(end {fmt(end[0])} {fmt(end[1])}) (width {fmt(TRACE_WIDTH_MM)}) '
        f'(layer "{layer}") (net {NET_CODE[net]}) (uuid {uid(key)}))'
    )


def route_pair(pin: int) -> list[str]:
    net = NET_BY_PIN[pin]
    start = global_pad("J1", pin)
    end = global_pad("J2", pin)
    direction = -1.0 if pin % 2 else 1.0
    layer = "F.Cu" if pin % 2 else "B.Cu"
    y_route = start[1] + direction * ROUTE_OFFSET_MM
    p1 = (start[0] + 1.15, y_route)
    p2 = (end[0] - 1.15, y_route)
    points = [start, p1, p2, end]
    return [segment(points[i], points[i + 1], layer, net, f"route-{pin}-{i}") for i in range(3)]


def build_board() -> str:
    board_left = min(global_pad("J1", pin)[0] for pin in range(1, 11)) - 2.0
    board_right = J2_ORIGIN[0] + 3.5
    board_top = J2_ORIGIN[1] - 6 * PITCH_MM - 0.92
    board_bottom = J1_ORIGIN[1] + 3.34

    nets = ['  (net 0 "")'] + [
        f'  (net {code} "{net}")' for net, code in NET_CODE.items()
    ]
    routes = []
    for pin in range(1, 11):
        routes.extend(route_pair(pin))

    # J2.12 branches to the existing PPS route at its horizontal segment.
    p12 = global_pad("J2", 12)
    pps_y = global_pad("J1", 7)[1] - ROUTE_OFFSET_MM
    branch = [p12, (109.0, board_top + 1.2), (board_right - 1.0, board_top + 1.2),
              (board_right - 1.0, pps_y), (108.85, pps_y)]
    for i in range(len(branch) - 1):
        routes.append(segment(branch[i], branch[i + 1], "F.Cu", NET_BY_PIN[7], f"pps-branch-{i}"))

    return f'''(kicad_pcb (version 20240108) (generator pcbnew)
  (general (thickness 0.8))
  (paper "A4")
  (layers
    (0 "F.Cu" signal)
    (31 "B.Cu" signal)
    (36 "B.SilkS" user "b.silkscreen")
    (37 "F.SilkS" user "f.silkscreen")
    (38 "B.Mask" user)
    (39 "F.Mask" user)
    (44 "Edge.Cuts" user)
    (46 "B.CrtYd" user "b.courtyard")
    (47 "F.CrtYd" user "f.courtyard")
    (48 "B.Fab" user)
    (49 "F.Fab" user)
  )
  (setup
    (stackup
      (layer "F.SilkS" (type "Top Silk Screen"))
      (layer "F.Mask" (type "Top Solder Mask"))
      (layer "F.Cu" (type "copper") (thickness 0.035))
      (layer "dielectric 1" (type "core") (thickness 0.73) (material "FR4") (epsilon_r 4.5) (loss_tangent 0.02))
      (layer "B.Cu" (type "copper") (thickness 0.035))
      (layer "B.Mask" (type "Bottom Solder Mask"))
      (layer "B.SilkS" (type "Bottom Silk Screen"))
      (copper_finish "None")
      (dielectric_constraints no))
    (pad_to_mask_clearance 0)
    (allow_soldermask_bridges_in_footprints no))
{chr(10).join(nets)}
{footprint('J1', 'COMPUTE BLADE', 'Connector_PinSocket_2.54mm:PinSocket_2x05_P2.54mm_Vertical', 5, 'B.Cu', J1_ORIGIN)}
{footprint('J2', 'DDA GPS/RTC', 'Connector_PinHeader_2.54mm:PinHeader_2x06_P2.54mm_Vertical', 6, 'F.Cu', J2_ORIGIN)}
  (gr_rect (start {fmt(board_left)} {fmt(board_top)}) (end {fmt(board_right)} {fmt(board_bottom)})
    (stroke (width 0.1) (type default)) (fill none) (layer "Edge.Cuts")
    (uuid {uid('board-outline')}))
  (gr_text "DDA GPS/RTC" (at {fmt(J2_ORIGIN[0] - 1.27)} {fmt(board_top + 0.6)} 0)
    (layer "F.SilkS") (uuid {uid('front-label-dda')})
    (effects (font (size 0.8 0.8) (thickness 0.13))))
  (gr_text "PPS -> GPIO4" (at {fmt((board_left + board_right) / 2)} {fmt(board_bottom - 1.3)} 0)
    (layer "F.SilkS") (uuid {uid('front-label-pps')})
    (effects (font (size 0.8 0.8) (thickness 0.13))))
  (gr_text "COMPUTE BLADE" (at {fmt(J1_ORIGIN[0] - 1.27)} {fmt(board_bottom - 1.3)} 0)
    (layer "B.SilkS") (uuid {uid('bottom-label-compute')})
    (effects (font (size 0.8 0.8) (thickness 0.13)) (justify mirror)))
{chr(10).join(routes)}
)\n'''


def build_report() -> str:
    lines = [
        "Compute Blade to DDA GPS/RTC adapter connectivity",
        "Physical header pin numbers only",
        "",
        "Pin     Net",
        "------- ---------------------------",
    ]
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
    print(f"J1/J2 centerline offset: {CONNECTOR_OFFSET_MM:.1f} mm")


if __name__ == "__main__":
    main()
