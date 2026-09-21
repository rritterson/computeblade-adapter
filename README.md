# Compute Blade ↔ DDA GPS/RTC adapter, upright revision

This repository contains a passive, two-connector KiCad adapter. The adapter PCB remains parallel to the Compute Blade PCB; a right-angle J2 turns the Dark Dragons Astronomy (DDA) GPS/RTC module through 90° so the DDA PCB stands upright and projects toward the Compute Blade's USB-C/right side. GPIO names are descriptions only: every connection below uses **physical header pin numbers**.

The project targets **KiCad 10.0.5** with the pinned `kicad/kicad:10.0.5-full` CI image. Local KiCad is not required.

> **Fabrication warning:** CI success is necessary, not sufficient. The DDA pin-1 orientation, actual connector stack height, Compute Blade revision, and BladeRunner installation position must be checked on real hardware before ordering more than a fit-check prototype.

## Assembly concept and connector choices

- **J1:** vertical 2x5 female socket, through-hole, on the adapter bottom. Candidate purchasing part: [Samtec SLW-105-01-G-D](https://www.samtec.com/products/slw-105-01-g-d), a 2.54 mm low-profile vertical socket with a published 0.180 in / 4.572 mm body height. The PCB uses KiCad's `Connector_PinSocket_2.54mm:PinSocket_2x05_P2.54mm_Vertical` footprint and its standard STEP model.
- **J2:** right-angle 2x6 male header, through-hole, on the adapter top. Candidate purchasing part: [Samtec TSW-106-08-G-D-RA](https://www.samtec.com/products/tsw-106-08-g-d-ra), a 2.54 mm, 12-pin, two-row right-angle header with a published 0.230 in / 5.842 mm mating post. The PCB uses KiCad's `Connector_PinHeader_2.54mm:PinHeader_2x06_P2.54mm_Horizontal` footprint and its standard STEP model.
- `J2_FOOTPRINT_ROTATION_DEG = 0.0` makes the KiCad footprint's local +X mating direction point toward assembly +X, defined here as the USB-C/right side.
- J1 and J2 pad-row centerlines remain 10.0 mm apart. Change `J2_CENTERLINE_OFFSET_MM` in `scripts/design_config.py` and regenerate to change this.
- The board is two-layer, 0.8 mm FR-4 with nominal 1 oz / 35 µm copper. Power and ground routes are 0.50 mm; signal routes are 0.25 mm.

The KiCad STEP models are dimensionally useful generic connector models, not manufacturer-controlled models for the two candidate orderable parts. Confirm the Samtec series prints, tail length, mating depth, and the Compute Blade header's exposed-post length before purchase.

## Exact electrical mapping

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

Thus J1.1↔J2.1 through J1.10↔J2.10 are exact physical-pin mappings, with the additional J2.12↔J1.7 connection. J1.7, J2.7, and J2.12 are one net. J2.11 is explicitly no-connect. J2.12 carries GPS PPS to Compute Blade physical pin 7 (GPIO4); RTC_INT on J2.11 is intentionally unused.

The DDA does not use J2 pins 2 or 4, but their requested copper connections remain present and separate. Energizing them at 5 V matches direct connection to the Compute Blade header. The adapter does not merge duplicate 5 V nets or duplicate GND nets.

## DDA orientation is explicit

`DDA_ROTATION_180 = False` in `scripts/design_config.py` selects the default mechanical envelope. `scripts/generate_mechanical_model.py` always produces both `dda_simple_default.stl` and `dda_simple_rot180.stl`; the validator can compare both with `--compare-variants`.

This parameter rotates only the measured DDA geometry around J2's +X mating axis. It **does not renumber J2 and does not alter the verified electrical design**. The 180° model currently fails the conservative lower BladeRunner clearance plane. More importantly, physically reversing a 2x6 socket can reverse which DDA contact reaches each male-header pin. Therefore the alternate is a diagnostic model, not a second fabrication variant. Do not select or manufacture it until DDA pin 1 has been confirmed from authoritative data or continuity measurement and the contact correspondence has been reviewed explicitly.

## Measured DDA model

The simplified collision model uses the supplied measurements as source-of-truth:

- PCB: 16.5 × 22.5 × 1.7 mm.
- Socket body: 15.6 mm along the six-pin row and 5.0 mm across the two rows.
- Top PCB edge to socket near edge: 2.5 mm.
- Top edge to row 1: 3.5 mm; row 2: 6.04 mm.
- First column center: 1.90 mm from the left edge, then 2.54 mm pitch.
- PCB surface to socket mating plane: 8.3 mm.
- **GNSS side:** conservative 4.0 mm full-face component envelope, facing toward the mating plane in the default model.
- **Battery/RTC side:** conservative 4.75 mm full-face component envelope, facing away from the mating plane in the default model.

These full-face component boxes intentionally overestimate the occupied volume. Pin numbering is not derived from this geometry.

## Official reference CAD and approximation boundary

`scripts/fetch_reference_cad.py` downloads files from the upstream Compute Blade repository at [immutable commit `9c7e472f4fb5c74401d17cdc7a766254d78a32c6`](https://github.com/uptime-lab/compute-blade/commit/9c7e472f4fb5c74401d17cdc7a766254d78a32c6) and rejects any SHA-256 mismatch. The selected files are:

- `models/blade/v1.0-mk4/v1.0_mk4_DEV.step`
- `models/bladerunner/19-inch/half body.stl`
- `models/bladerunner/19-inch/left bracket.stl`
- `models/bladerunner/19-inch/right bracket.stl`

The files are downloaded into ignored `mechanical/reference/` storage rather than committed. The official 19-inch half-body mesh measures 224.12 × 297.19 × 46.50 mm; validation reserves 1.5 mm at each Z limit. The validator authenticates the official STEP, checks its millimetre units and J3 assembly product, and authenticates/parses the BladeRunner meshes.

This is not full B-Rep interference analysis. `scripts/validate_geometry.py` aligns documented conservative boxes to a J1-centered assembly frame, where +X is right, the blade PCB occupies X≤0, and the adapter is 8.5 mm above the blade reference plane. It then checks:

1. selected DDA boxes do not intersect the conservative blade PCB or nearby-component keepouts;
2. DDA, adapter, and simplified connector boxes stay inside the conservative BladeRunner Y/Z envelope;
3. the DDA is wholly on the +X/right side of J2;
4. J2 is the right-angle footprint at the explicit rotation;
5. the socket mating face and 8.3 mm DDA PCB offset agree with the connector frame.

The 8.5 mm J1 stack height, the STEP-to-J1 alignment, and the simplified nearby-component boxes are documented engineering assumptions, not measurements extracted by a solid CAD kernel. They require a physical spot-check.

## Regeneration and validation

Python 3.9 or later is sufficient for the deterministic generators and conservative checks:

```sh
python3 scripts/fetch_reference_cad.py
python3 scripts/generate_schematic.py
python3 scripts/generate_or_update_pcb.py
python3 scripts/generate_mechanical_model.py
python3 scripts/verify_connectivity.py
python3 scripts/validate_geometry.py --compare-variants
python3 -m unittest discover -s scripts -p 'test_*.py' -v
```

The connectivity verifier independently parses symbol pin geometry and labels, PCB pad nets, and routed copper. It fails on any requested mapping error, J2.11 connection, power-rail short, GPIO-to-power short, or unrouted connector pad.

## GitHub Actions

`.github/workflows/pcb-ci.yml` runs on push, pull request, and manual dispatch. It fetches and authenticates upstream CAD, regenerates all deterministic files, runs Python tests, verifies connectivity, runs KiCad ERC and DRC, runs the selected geometry validation, exports schematic and PCB views, generates Gerbers and Excellon drill files, and packages `compute-blade-dda-adapter-gerbers.zip`.

After a successful run, download `compute-blade-dda-adapter-manufacturing` from the run's **Artifacts** section for fabrication files, and `compute-blade-dda-adapter-reports` for ERC/DRC/connectivity/geometry reports, board views, and both orientation diagrams.

Passing ERC/DRC does not validate mechanics. Passing the geometry script still depends on simplified solids and the stated alignment assumptions. Confirm DDA pin 1, connector mating direction, J1 stack height, component-side orientation, chassis installation position, and real clearances before fabrication.
