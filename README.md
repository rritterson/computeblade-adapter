# Compute Blade ↔ DDA GPS/RTC adapter — parallel-DDA revision

This repository contains a passive two-connector KiCad adapter that remaps the Dark Dragons Astronomy GPS PPS signal while keeping the unmodified DDA PCB parallel to the Compute Blade PCB. Physical connector pin numbers are authoritative; GPIO names are descriptions and are never interpreted as BCM pin numbers.

The project targets **KiCad 10.0.5** through the pinned `kicad/kicad:10.0.5-full` CI image.

> Passing connectivity, ERC, DRC, CAD collision, and clearance checks is required but does not make this design fabrication-ready. Reverse-use connector behavior, seating forces, and final BladeRunner fit still require a physical prototype.

## Approved architecture

- **J1:** Samtec `HLE-105-02-L-DV-PE-BE`, 2×5, 2.54 mm, bottom-entry/pass-through receptacle.
- **J2:** Samtec `MTLW-106-06-G-D-035`, 2×6, 2.54 mm, reverse-mounted/pass-through male header.
- Adapter: 2-layer 0.6 mm FR-4, nominal 1 oz / 35 µm copper.
- Compute Blade, adapter, and DDA PCB planes are all XY.
- DDA socket/battery face points inward (−Z), toward the adapter and Compute Blade.
- DDA GNSS face points outward (+Z), toward the neighboring blade.
- The DDA remains electrically and mechanically unmodified.

The exact footprints are project-local in `pcb/Adapter.pretty/`. They use the manufacturer 2.54 mm patterns, explicit fab outlines, courtyards, 1.0 mm drills, and 1.8 mm pads. That gives a nominal 0.40 mm annular ring, compatible with ordinary 0.6 mm two-layer service at many board houses. The selected fabricator must still confirm 0.6 mm stock, 1.0 mm plated drills, and its finished-hole/annular-ring rules before ordering.

The generated connector STEP models are manufacturer-dimensioned approximations because exact configured Samtec CAD is not available to deterministic unauthenticated CI. They are not substitutes for a first-article fit test.

## Coordinate and orientation contract

```text
X = Compute Blade long axis
Y = Compute Blade width
Z = outward normal from the Compute Blade PCB

Compute Blade PCB plane = XY
adapter PCB plane       = XY
DDA PCB plane           = XY
DDA PCB normal          = +Z
DDA socket mating axis  = -Z toward adapter
J2 mating posts         = +Z
J2 six-position axis    = +X
J2 row 1 → row 2        = -Y
```

The shared DDA transform is the identity basis:

```text
[[1, 0, 0],
 [0, 1, 0],
 [0, 0, 1]]
```

`scripts/design_config.py` is the sole parameter source used by the PCB generator, geometry validator, STEP generator, SVG generator, and PNG renderer. Unit tests hard-fail if the DDA becomes upright, the GNSS face points inward, the mating direction reverses, or J2’s columns/rows change axes.

## Exact physical-pin mapping

| Physical pin | J1 Compute Blade | J2 DDA | Adapter net |
|---:|---|---|---|
| 1 | 3V3 | 3V3 | `3V3` |
| 2 | 5V | unused by DDA | `5V_PIN2` |
| 3 | GPIO2 / SDA | SDA | `SDA_GPIO2` |
| 4 | 5V | unused by DDA | `5V_PIN4` |
| 5 | GPIO3 / SCL | SCL | `SCL_GPIO3` |
| 6 | GND | GND | `GND_PIN6` |
| 7 | GPIO4 / PPS_IN | unused DDA position | `PPS_GPIO4` |
| 8 | GPIO14 / UART_TX | GPS_RX | `UART_TX_TO_GPS_RX` |
| 9 | GND | unused by DDA | `GND_PIN9` |
| 10 | GPIO15 / UART_RX | GPS_TX | `UART_RX_FROM_GPS_TX` |
| 11 | — | RTC_INT | **NC** |
| 12 | — | GPS_PPS | `PPS_GPIO4` |

Pins J1.1–J1.10 map one-for-one to J2.1–J2.10. J2.12 additionally joins J1.7/J2.7, so GPS PPS reaches Compute Blade physical pin 7 / GPIO4. J2.11 remains explicitly unconnected. Duplicate rails remain separate: `5V_PIN2`, `5V_PIN4`, `GND_PIN6`, and `GND_PIN9` are not merged by the adapter.

## Dimension provenance and stack calculation

Physically measured Compute Blade dimensions:

- PCB surface to header-plastic top: 2.500 mm.
- PCB surface to pin tip: 9.000 mm.
- Exposed post: 6.500 mm.

Manufacturer HLE requirements:

- Bottom-entry minimum reach: 2.590 mm plus host PCB thickness.
- With a 0.600 mm adapter, required reach is 3.190 mm.
- The measured 6.500 mm post exceeds this requirement by 3.310 mm.
- `-PE-BE` is open/pass-through, so excess post does not bottom in a closed socket.
- Adapter underside is 2.500 mm above the Compute Blade PCB, with `J1_SEATING_GAP_MM = 0.0`.

Manufacturer MTLW geometry:

```text
OAL                                      7.620 mm
insulator                                1.520 mm
-035 lower segment                       0.889 mm
reverse upper/DDA mating segment         5.211 mm
DDA insertion                            3.400 mm
free post after insertion                1.811 mm
lower post tip above blade PCB           0.091 mm
```

The segment normally treated as the MTLW tail is used as the DDA mating post. The selected `-G` configuration provides plating on this reverse-used segment, but its contact wear, retention, and long-term behavior in this unconventional role remain prototype-validation items.

Measured DDA geometry:

- PCB: 16.5 × 22.5 × **1.6 mm**.
- Socket mating face to socket-side PCB surface: 8.3 mm.
- Socket-side PCB surface to GNSS top: **4.0 mm total**.
- GNSS projection beyond the opposite PCB surface: 2.4 mm.
- Battery/RTC inward local envelope: 4.75 mm.

The 4.0 mm value already includes the 1.6 mm PCB. It must not be calculated as `1.6 + 4.0`.

```text
adapter underside                                  2.500 mm
+ MTLW OAL - body - lower segment - insertion      1.811 mm
= DDA socket mating face                           4.311 mm
+ mating face to socket-side PCB surface           8.300 mm
+ socket-side surface to GNSS top                  4.000 mm
= total outward stack                             16.611 mm
```

## Placement and BladeRunner clearance

The official Compute Blade STEP anchors J3 at `(133.075077, 18.325065, 0.0)` mm. The selected complete DDA projection is:

```text
X = 160.000 .. 176.500 mm
Y =  19.500 ..  42.000 mm
```

The validator extracts the official PCB solid bounds from the STEP and requires the full DDA PCB, socket, GNSS envelope, and inward battery envelope to remain inside its XY footprint with a 0.5 mm configured margin.

BladeRunner clearance uses the physical slit-edge result, not slit centerline pitch:

```text
physical per-blade clearance       19.9317 mm
safety reserve                      1.0000 mm
design maximum                     18.9317 mm
approved outward stack             16.6110 mm
physical nominal clearance          3.3207 mm
margin after 1.0 mm reserve         2.3207 mm
```

CI authenticates the pinned official `half body.stl`, rechecks its mesh encoding, triangle count, hash, and outer bounds, and applies the previously slit-edge-derived 19.9317 mm physical clearance. It does not substitute the obsolete `(-1.5, 45.0)` clearance box or the former 36 mm total-depth rule.

## Official CAD and mechanical validation

`scripts/fetch_reference_cad.py` authenticates upstream CAD at immutable Compute Blade commit `9c7e472f4fb5c74401d17cdc7a766254d78a32c6`:

- `models/blade/v1.0-mk4/v1.0_mk4_DEV.step`
- `models/bladerunner/19-inch/half body.stl`
- `models/bladerunner/19-inch/left bracket.stl`
- `models/bladerunner/19-inch/right bracket.stl`

Pure-Python validation checks the shared transforms, pin-1 mapping, connector reach, 3.40 mm insertion, lower-post clearance, DDA XY keep-in, 16.611 mm stack, and BladeRunner margins. The CadQuery assembly stage additionally intersects the DDA, J2, and adapter-outside-J1 region against the exact official Compute Blade B-Rep and fails on material overlap.

The confirmed DDA pin-1 orientation remains:

- readable GNSS/component side: bottom-left;
- underside/socket-hole view: bottom-right.

This is encoded independently of electrical net names.

## Inspecting the assembly

`scripts/generate_assembly_model.py` produces:

- `mechanical/generated/full_assembly.step`
- `mechanical/generated/full_assembly_lightweight.step`
- `mechanical/generated/full_assembly_with_bladerunner.step`
- standalone J1/J2 approximation STEP models
- top, side, end, isometric, J1-closeup, and J2/DDA-closeup PNGs

The full assembly imports the exact official Compute Blade B-Rep. The BladeRunner-context assembly adds the validated 18.9317 mm design plane and 19.9317 mm physical-clearance plane. All placement uses the same boxes and transforms as `validate_geometry.py`; there is no separate visual-only placement.

Open the STEP files in FreeCAD. From a successful GitHub Actions run, download the `compute-blade-dda-adapter-reports` artifact for the STEP files, fixed renders, manifests, ERC/DRC reports, and board views. The visual model is an inspection aid and does not replace a physical prototype.

## Regeneration and CI

```sh
python3 scripts/fetch_reference_cad.py
python3 scripts/generate_schematic.py
python3 scripts/generate_or_update_pcb.py
python3 scripts/generate_mechanical_model.py
python3 scripts/verify_connectivity.py
python3 -m unittest discover -s scripts -p 'test_*.py' -v
python3 scripts/validate_geometry.py
python3 -m pip install --requirement requirements-assembly.txt
python3 scripts/generate_assembly_model.py
```

GitHub Actions repeats deterministic generation, connectivity verification, unit tests, geometry validation, STEP round-trip checks, blank-render checks, KiCad ERC/DRC, Gerber export, and Excellon drill export. Download `compute-blade-dda-adapter-manufacturing` for `compute-blade-dda-adapter-gerbers.zip`; the BOM is included in `compute-blade-dda-adapter-reports`.

## Prototype-only risks

- Reverse-use MTLW contact plating, wear, and retention behavior.
- Actual HLE seating against the Compute Blade header plastic and practical soldering on 0.6 mm FR-4.
- Physical connector insertion and extraction forces.
- Residual differences between simplified connector bodies and production parts.
- Final assembled fit in a real 19-inch BladeRunner, including manufacturing and seating tolerances.
- First-article confirmation before ordering multiple boards.

The project must not be described as fabrication-ready until those physical checks are closed.
