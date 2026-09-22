#!/usr/bin/env python3
"""Generate the small, deterministic KiCad schematic and project metadata."""

from __future__ import annotations

import json
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PCB_DIR = ROOT / "pcb"
PROJECT_NAME = "compute-blade-dda-adapter"
SCHEMATIC = PCB_DIR / f"{PROJECT_NAME}.kicad_sch"
PROJECT = PCB_DIR / f"{PROJECT_NAME}.kicad_pro"
SYMBOL_LIBRARY = PCB_DIR / "Adapter.kicad_sym"
SYMBOL_TABLE = PCB_DIR / "sym-lib-table"
FOOTPRINT_TABLE = PCB_DIR / "fp-lib-table"
UUID_NAMESPACE = uuid.UUID("1b3ef2d8-4948-4c5f-a6a4-cbc14a42e582")

NETS = {
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


def stable_uuid(name: str) -> str:
    return str(uuid.uuid5(UUID_NAMESPACE, name))


def effects(hidden: bool = False) -> str:
    suffix = " hide" if hidden else ""
    return f'(effects (font (size 1.27 1.27)){suffix})'


def library_symbol(name: str, rows: int, *, qualified: bool = True) -> str:
    half_height = (rows + 1) * 1.27
    symbol_name = f"Adapter:{name}" if qualified else name
    pins = []
    for row in range(rows):
        y = (rows - 1 - 2 * row) * 1.27
        odd = row * 2 + 1
        even = odd + 1
        pins.append(
            f'''      (pin passive line (at -5.08 {y:.2f} 0) (length 2.54)
        (name "Pin_{odd}" {effects()})
        (number "{odd}" {effects()}))
      (pin passive line (at 5.08 {y:.2f} 180) (length 2.54)
        (name "Pin_{even}" {effects()})
        (number "{even}" {effects()}))'''
        )
    return f'''    (symbol "{symbol_name}"
      (pin_names (offset 1.016) hide)
      (exclude_from_sim no)
      (in_bom yes)
      (on_board yes)
      (property "Reference" "J" (at 0 {half_height + 1.27:.2f} 0) {effects()})
      (property "Value" "{name}" (at 0 {-half_height - 1.27:.2f} 0) {effects()})
      (property "Footprint" "" (at 0 0 0) {effects(True)})
      (property "Datasheet" "~" (at 0 0 0) {effects(True)})
      (property "Description" "Passive double-row connector, physical odd/even numbering" (at 0 0 0) {effects(True)})
      (symbol "{name}_0_1"
        (rectangle (start -2.54 {half_height:.2f}) (end 2.54 {-half_height:.2f})
          (stroke (width 0) (type default))
          (fill (type background))))
      (symbol "{name}_1_1"
{chr(10).join(pins)})
    )'''


def pin_position(cx: float, cy: float, rows: int, pin: int) -> tuple[float, float]:
    row = (pin - 1) // 2
    x = cx - 5.08 if pin % 2 else cx + 5.08
    y = cy + (rows - 1 - 2 * row) * 1.27
    return x, y


def placed_symbol(ref: str, value: str, lib_name: str, footprint: str,
                  cx: float, cy: float, pins: int) -> str:
    pin_entries = "\n".join(
        f'    (pin "{pin}" (uuid {stable_uuid(f"{ref}-pin-{pin}")}))'
        for pin in range(1, pins + 1)
    )
    return f'''  (symbol (lib_id "Adapter:{lib_name}") (at {cx:.2f} {cy:.2f} 0) (unit 1)
    (exclude_from_sim no) (in_bom yes) (on_board yes) (dnp no)
    (uuid {stable_uuid(ref)})
    (property "Reference" "{ref}" (at {cx:.2f} {cy - 10.16:.2f} 0) {effects()})
    (property "Value" "{value}" (at {cx:.2f} {cy + 10.16:.2f} 0) {effects()})
    (property "Footprint" "{footprint}" (at {cx:.2f} {cy:.2f} 0) {effects(True)})
    (property "Datasheet" "~" (at {cx:.2f} {cy:.2f} 0) {effects(True)})
    (property "Description" "Physical pin numbering; do not reinterpret as BCM numbering" (at {cx:.2f} {cy:.2f} 0) {effects(True)})
{pin_entries}
    (instances
      (project "{PROJECT_NAME}"
        (path "/{stable_uuid('root-sheet')}" (reference "{ref}") (unit 1))))
  )'''


def label(name: str, x: float, y: float, key: str) -> str:
    return f'''  (label "{name}" (at {x:.2f} {y:.2f} 0)
    {effects()}
    (uuid {stable_uuid(key)}))'''


def build_schematic() -> str:
    j1_center = (60.96, 76.20)
    j2_center = (111.76, 76.20)
    labels = []
    for pin, net in NETS.items():
        x, y = pin_position(*j1_center, 5, pin)
        labels.append(label(net, x, y, f"J1-label-{pin}"))
        x, y = pin_position(*j2_center, 6, pin)
        labels.append(label(net, x, y, f"J2-label-{pin}"))
    x12, y12 = pin_position(*j2_center, 6, 12)
    labels.append(label(NETS[7], x12, y12, "J2-label-12"))
    x11, y11 = pin_position(*j2_center, 6, 11)

    j1_fp = "Adapter:Samtec_HLE-105-02-L-DV-PE-BE"
    j2_fp = "Adapter:Samtec_MTLW-106-06-G-D-035_Reverse"
    return f'''(kicad_sch (version 20231120) (generator eeschema)
  (uuid {stable_uuid('root-sheet')})
  (paper "A4")
  (title_block
    (title "Compute Blade to DDA GPS/RTC passive adapter")
    (date "2026-09-21")
    (rev "0.3-parallel")
    (company "Open hardware reference design")
    (comment 1 "PHYSICAL HEADER PIN NUMBERS ONLY"))
  (lib_symbols
{library_symbol('Conn_02x05_Odd_Even', 5)}
{library_symbol('Conn_02x06_Odd_Even', 6)}
  )
{chr(10).join(labels)}
  (no_connect (at {x11:.2f} {y11:.2f}) (uuid {stable_uuid('J2-no-connect-11')}))
{placed_symbol('J1', 'HLE-105-02-L-DV-PE-BE', 'Conn_02x05_Odd_Even', j1_fp, *j1_center, 10)}
{placed_symbol('J2', 'MTLW-106-06-G-D-035 REVERSE', 'Conn_02x06_Odd_Even', j2_fp, *j2_center, 12)}
  (text "Physical pins 1-10 map one-to-one. J2.12 joins J1.7/J2.7; J2.11 is NC. DDA is parallel."
    (exclude_from_sim no) (at 86.36 101.60 0)
    (effects (font (size 1.27 1.27)) (justify bottom)))
  (sheet_instances
    (path "/" (page "1")))
)\n'''


def build_symbol_library() -> str:
    symbols = "\n".join(
        (
            library_symbol("Conn_02x05_Odd_Even", 5, qualified=False),
            library_symbol("Conn_02x06_Odd_Even", 6, qualified=False),
        )
    )
    return f'''(kicad_symbol_lib (version 20231120) (generator kicad_symbol_editor)
{symbols}
)\n'''


def build_symbol_table() -> str:
    return '''(sym_lib_table
  (version 7)
  (lib (name "Adapter")(type "KiCad")(uri "${KIPRJMOD}/Adapter.kicad_sym")(options "")(descr "Project-local passive connector symbols"))
)\n'''


def build_footprint_table() -> str:
    return '''(fp_lib_table
  (version 7)
  (lib (name "Adapter")(type "KiCad")(uri "${KIPRJMOD}/Adapter.pretty")(options "")(descr "Project-local manufacturer-dimensioned Samtec connector footprints"))
)\n'''


def build_project() -> str:
    project = {
        "board": {},
        "boards": [],
        "cvpcb": {},
        "erc": {},
        "libraries": {},
        "meta": {"filename": f"{PROJECT_NAME}.kicad_pro", "version": 1},
        "net_settings": {
            "classes": [
                {
                    "bus_width": 12,
                    "clearance": 0.15,
                    "diff_pair_gap": 0.25,
                    "diff_pair_via_gap": 0.25,
                    "diff_pair_width": 0.20,
                    "line_style": 0,
                    "microvia_diameter": 0.30,
                    "microvia_drill": 0.10,
                    "name": "Default",
                    "pcb_color": "rgba(0, 0, 0, 0.000)",
                    "schematic_color": "rgba(0, 0, 0, 0.000)",
                    "track_width": 0.25,
                    "via_diameter": 0.80,
                    "via_drill": 0.40,
                    "wire_width": 6,
                }
            ],
            "meta": {"version": 3},
            "net_colors": None,
            "netclass_assignments": None,
            "netclass_patterns": [],
        },
        "pcbnew": {},
        "schematic": {},
        "sheets": [],
        "text_variables": {},
    }
    return json.dumps(project, indent=2, sort_keys=True) + "\n"


def main() -> None:
    PCB_DIR.mkdir(parents=True, exist_ok=True)
    SCHEMATIC.write_text(build_schematic(), encoding="utf-8")
    PROJECT.write_text(build_project(), encoding="utf-8")
    SYMBOL_LIBRARY.write_text(build_symbol_library(), encoding="utf-8")
    SYMBOL_TABLE.write_text(build_symbol_table(), encoding="utf-8")
    FOOTPRINT_TABLE.write_text(build_footprint_table(), encoding="utf-8")
    print(f"Wrote {SCHEMATIC.relative_to(ROOT)}")
    print(f"Wrote {PROJECT.relative_to(ROOT)}")
    print(f"Wrote {SYMBOL_LIBRARY.relative_to(ROOT)}")
    print(f"Wrote {SYMBOL_TABLE.relative_to(ROOT)}")
    print(f"Wrote {FOOTPRINT_TABLE.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
