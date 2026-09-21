# Compute Blade to DDA GPS/RTC adapter

This repository contains a passive, two-connector KiCad adapter that shifts a Dark Dragons Astronomy (DDA) GPS/RTC module inward from the edge of a Compute Blade. It uses **physical header pin numbers only**; GPIO names are descriptions, never pin-number substitutions.

The project targets **KiCad 10.0.5** on the current stable KiCad 10 series. This is the newest immutable patch tag currently published for the official `kicad/kicad` Docker image; pinning it avoids a floating CI toolchain. Local KiCad is not required: GitHub Actions performs connectivity checks, ERC, DRC, plots, and manufacturing export with that container.

> **Fabrication warning:** connector body dimensions, mating direction, component-side orientation, Compute Blade keep-outs, DDA board outline, and BladeRunner chassis clearance must be checked against real hardware or authoritative mechanical drawings. Generated files and even passing ERC/DRC do not make the design fabrication-ready.

## Electrical mapping

| Physical pin | J1 Compute Blade meaning | J2 DDA meaning | Adapter net |
|---:|---|---|---|
| 1 | 3V3 | 3V3 | `3V3` |
| 2 | 5V | unused | `5V_PIN2` |
| 3 | GPIO2 / SDA | SDA | `SDA_GPIO2` |
| 4 | 5V | unused | `5V_PIN4` |
| 5 | GPIO3 / SCL | SCL | `SCL_GPIO3` |
| 6 | GND | GND | `GND_PIN6` |
| 7 | GPIO4 / PPS_IN | unused on DDA | `PPS_GPIO4` |
| 8 | GPIO14 / UART_TX | GPS_RX | `UART_TX_TO_GPS_RX` |
| 9 | GND | pass-through | `GND_PIN9` |
| 10 | GPIO15 / UART_RX | GPS_TX | `UART_RX_FROM_GPS_TX` |
| 11 | — | RTC_INT | **NC** |
| 12 | — | GPS_PPS | `PPS_GPIO4` |

J2.12 is intentionally tied to J1.7 and J2.7 so the DDA GPS PPS output reaches Compute Blade physical pin 7 (GPIO4). J2.11 is intentionally and explicitly marked no-connect because RTC_INT is not used.

The DDA does not use J2 pins 2 or 4, but the adapter intentionally preserves the requested J1-to-J2 copper connections on the separate `5V_PIN2` and `5V_PIN4` nets. Energizing those pins at 5 V is therefore expected and matches what would happen if the DDA were connected directly to the board header. Duplicate 5 V and GND connections are not merged together by the adapter; they may already be common on the attached products.

## Mechanical and fabrication assumptions

- Two copper layers, 0.8 mm FR-4, nominal 1 oz / 35 µm copper.
- J1 is a through-hole 2x5 female socket on the bottom, mating downward.
- J2 is a through-hole 2x6 male header on the top, mating upward.
- Both use 2.54 mm pitch, odd/even physical pin numbering, and standard KiCad footprints.
- The connectors are parallel. `CONNECTOR_OFFSET_MM = 10.0` in `scripts/generate_or_update_pcb.py` is the single source for the lateral centerline offset. Change that value and rerun the script to update placement, outline, labels, and routing.
- “Inward” is represented by positive board X from J1 toward J2. Which physical Compute Blade edge this corresponds to must be confirmed during mechanical fit checking.
- The PCB outline is intentionally compact but provisional until connector-body and chassis measurements are confirmed.

## Regeneration and local checks

Python 3.9 or later is sufficient for deterministic generation and the independent connectivity check:

```sh
python3 scripts/generate_schematic.py
python3 scripts/generate_or_update_pcb.py
python3 scripts/verify_connectivity.py
```

The verifier parses embedded symbol pin geometry and schematic labels, then separately parses PCB footprint pad net assignments. It checks the exact equivalence classes, the intentional NC, power-rail isolation, and GPIO-to-power isolation. It prints a complete J1/J2 table and exits nonzero on any mismatch.

## GitHub Actions

`.github/workflows/pcb-ci.yml` runs for pushes, pull requests, and manual dispatch. It uses the pinned `kicad/kicad:10.0.5` container to run schematic ERC and PCB DRC with violation exit codes, export schematic PDF and front/back board SVGs, generate Gerbers and Excellon drill files, and package manufacturing outputs as `compute-blade-dda-adapter-gerbers.zip`.

After a successful run, open the workflow run’s **Artifacts** section and download `compute-blade-dda-adapter-manufacturing` for the ZIP, or `compute-blade-dda-adapter-reports` for ERC/DRC reports and renders. CI success is required validation, but physical fit and orientation remain separate sign-off items.
