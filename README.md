# Compute Blade ↔ DDA GPS/RTC adapter, upright revision

This repository contains a passive, two-connector KiCad adapter. The adapter PCB remains parallel to the Compute Blade PCB; right-angle J2 turns the Dark Dragons Astronomy (DDA) GPS/RTC module through 90° so it stands upright in the IMG_0542-style orientation and projects toward the blade's top/interior **+Y** side. GPIO names are descriptions only: every connection uses **physical header pin numbers**.

The project targets **KiCad 10.0.5** with the pinned `kicad/kicad:10.0.5-full` CI image. Local KiCad is not required.

> **Fabrication warning:** CI success is necessary, not sufficient. Connector-body seating, the DDA socket's internal contact geometry, final STEP alignment, and installed BladeRunner clearance still require a fit-check prototype. Do not order multiple boards solely because ERC, DRC, and simplified geometry validation pass.

## Assembly and connector choices

- **J1:** [Samtec SLW-105-01-G-D](https://www.samtec.com/products/slw-105-01-g-d), a vertical 2x5 female through-hole socket on the adapter bottom. The PCB uses KiCad's `Connector_PinSocket_2.54mm:PinSocket_2x05_P2.54mm_Vertical` footprint and generic standard STEP model.
- **J2:** [Samtec TSW-106-08-G-D-RA](https://www.samtec.com/products/tsw-106-08-g-d-ra), a right-angle 2x6 male through-hole header on the adapter top. The PCB uses KiCad's `Connector_PinHeader_2.54mm:PinHeader_2x06_P2.54mm_Horizontal` footprint and generic standard STEP model.
- `J2_FOOTPRINT_ROTATION_DEG = -90.0` in KiCad's Y-down board coordinates maps J2's local +X mating posts to assembly +Y, toward the top/interior side.
- `J2_CENTERLINE_OFFSET_MM = 22.7` places J2's pin-1 origin so its six positions still occupy the former X span of 10.0…22.7 mm after the connector is turned 180° in-plane. This prevents J1/J2 footprint overlap while retaining the established connector region.
- `J2_Y_INSET_MM = -0.5` shifts the J2 origin slightly inward so the far side of the DDA retains at least the configured 0.5 mm PCB-edge margin.
- The board is two-layer, 0.8 mm FR-4 with nominal 1 oz / 35 µm copper. Power and ground routes are 0.50 mm; signal routes are 0.25 mm.

The KiCad 3D connector models are not manufacturer-controlled models for these exact orderable parts. Samtec offers configured CAD through its product portal, but the repository validates dimensions available in its manufacturer series drawings and conservatively models the remaining interface.

The selected `-08` is physically the required conventional double-row right-angle topology: solder tails enter the horizontal adapter in Z, mating posts point +Y, six positions run parallel to X, and the mating rows stack in Z. Samtec specifies a 0.230 in / 5.842 mm mating post and 0.090 in / 2.286 mm tail. The evaluated [TSW-106-09-G-D-RA](https://www.samtec.com/products/tsw-106-09-g-d-ra) has the same 5.842 mm mating post but a 0.290 in / 7.366 mm tail. It adds 5.08 mm of unnecessary below-board tail without improving DDA engagement, so it is not mechanically preferable here.

## Coordinate system and axis-derived DDA placement

One coordinate convention is used by PCB placement, collision validation, STEP export, SVG generation, and PNG rendering:

```text
X = Compute Blade long axis
Y = Compute Blade width
Z = outward normal from the Compute Blade PCB, toward the reference top-view camera
DDA PCB plane = XZ
DDA socket mating axis = +Y, toward the top/interior side
six connector columns = -X (parallel to the blade X axis)
row 1 to row 2 = -Z
J2 solder tails = +Z into the adapter PCB
```

The reference photograph is authoritative for orientation. Placement is derived from the final physical axis constraints rather than selected by interpreting Euler angles. The DDA-local X axis follows its six-pin row, local Y runs from its measured top edge toward its bottom edge, and local Z runs from the socket mating face toward the DDA PCB. The resulting local-to-assembly basis is:

```text
basis = [[-1, 0, 0],
         [ 0, 0, 1],
         [0, 1,  0]]
```

`DDA_COLUMN_AXIS`, `DDA_TOP_TO_BOTTOM_AXIS`, `DDA_PCB_NORMAL`, `DDA_SOCKET_MATING_AXIS`, and the matching J2 axes in `scripts/design_config.py` are the single source used by validation, STEP/SVG generation, and PNG rendering. CI derives vectors from modeled pin centers and hard-fails unless the DDA PCB normal is +Y, columns are −X, socket/J2 mating is +Y, J2 row 1→2 is −Z, and solder tails are +Z. Mutation tests reject a wrong PCB normal, reversed mating direction, or rows separated in Y.

The validator extracts the exact `Board` solid from the pinned Compute Blade STEP. Its global PCB bounds are X `0.006..250.016` mm and Y `0.006..42.505` mm. Relative to J3, the selected complete DDA envelope is X `8.100..24.600` mm and Y `8.632..23.382` mm. It therefore has 26.951 mm clearance to the PCB −Y edge and 0.798 mm to the +Y edge. `DDA_PCB_ENVELOPE_MARGIN_MM = 0.5` is enforced against the PCB outline for the PCB, socket, and both component keepouts. A regression mutation reflects the DDA into −Y and must fail the −Y-edge check.

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

J1.1↔J2.1 through J1.10↔J2.10 are exact physical-pin mappings, with J2.12 additionally tied to J1.7. Thus J1.7, J2.7, and J2.12 are one net. J2.11 is explicitly no-connect. J2.12 carries GPS PPS to Compute Blade physical pin 7 (GPIO4); J2.11 RTC_INT is intentionally unused.

The DDA does not use pins 2 or 4, but their requested copper connections remain present and separate. Energizing them at 5 V matches direct connection to the Compute Blade header. The adapter does not merge the duplicate 5 V nets or duplicate GND nets.

## Confirmed DDA pin-1 orientation

DDA pin 1 is physically confirmed:

- looking into the connector holes from the DDA PCB underside, with the connector horizontal, pin 1 is **bottom-right**;
- looking from the top/component side with “Dark Dragons” readable, pin 1 is **bottom-left**.

The DDA geometric row farther from its measured top PCB edge (6.04 mm) is therefore the physical-pin-1 row. The Samtec TSW series drawing identifies physical pin 1 as the upper mating row in a double-row right-angle part. The selected assembly maps those same physical positions; CI checks the footprint rotation, pad 1 and pad 2 coordinates, TSW upper/lower row relationship, DDA top/underside views, and selected orientation. Electrical pins are never inferred or renumbered from this geometry.

`DDA_ROTATION_180 = False` is the confirmed/default assembly. The generator still creates a `rot180` collision model around J2's +Y mating axis for comparison, but selecting it fails validation because it contradicts the confirmed pin-1 orientation (and crosses the conservative lower BladeRunner clearance). The alternate is diagnostic only, not an electrical or fabrication variant.

## Dimension provenance

### Physically measured

- Compute Blade PCB surface to header-plastic top: **2.5 mm**.
- Compute Blade PCB surface to male-pin tip: **9.0 mm**.
- Exposed male post above the plastic: **6.5 mm**.
- DDA PCB: 16.5 × 22.5 × 1.7 mm.
- DDA socket body: 15.6 mm along the six-pin row and 5.0 mm across rows.
- DDA top edge to socket near edge: 2.5 mm; row centerlines: 3.5 mm and 6.04 mm.
- First column center: 1.90 mm from the left edge, then 2.54 mm pitch.
- DDA PCB surface to socket mating face: 8.3 mm.
- Conservative component envelopes: GNSS side 4.0 mm and battery/RTC side 4.75 mm.

### Manufacturer-specified

The [SLW manufacturer series drawing](https://suddendocs.samtec.com/prints/slw-1xx-01-x-x-mkt.pdf) gives a 0.180 in / **4.572 mm** body and 0.085–0.115 in / **2.16–2.92 mm** acceptable insertion depth. The measured 6.5 mm exposed Compute Blade post exceeds the 2.16 mm minimum; CI asserts this.

The [TSW manufacturer series drawing](https://suddendocs.samtec.com/prints/tsw-xxx-xx-xxx-x-xx-xxx-mkt.pdf) gives the `-08` right-angle post as nominally 0.230 in / **5.842 mm**, its tail as 0.090 in / **2.286 mm**, the double-row body height as 0.219 in / **5.56 mm** reference, locates pin 1 at 0.040 in / **1.0 mm** reference from the corresponding body edge, and shows physical pin 1 as the upper right-angle row. The exact product page confirms 12 pins, two rows, right-angle orientation, 2.54 mm pitch, and 0.635 mm square posts. CI asserts Z-stacked mating rows, +Z solder tails, and the DDA/J2 +Y mating axis in addition to engagement and body clearance.

### User-defined acceptance requirement

The DDA socket is physically known to accept at least the Compute Blade's full **6.5 mm** exposed post. Although its spring contacts begin retaining before full seating, the user's conservative minimum for strong seating and retention is the point where no more than **3.1 mm** remains exposed:

```text
6.500 mm Compute Blade exposed post
- 3.100 mm maximum acceptable remaining exposure
= 3.400 mm DDA minimum acceptable insertion
```

`DDA_MIN_ACCEPTABLE_INSERTION_MM = 3.40` is a design requirement and CI assertion, not an estimated contact depth. Against the TSW's 5.842 mm mating post:

```text
5.842 mm TSW mating post
- 3.400 mm required DDA insertion
= 2.442 mm remaining free post length
```

The post-length calculation proves sufficient usable pin length only. The separate body-clearance check places the DDA socket at exactly 3.40 mm insertion and tests it against a conservative simplified TSW plastic-body/right-angle-elbow keepout.

### Calculated

The nominal adapter-PCB underside height above the Compute Blade PCB is:

```text
2.500 mm measured header-plastic height
+ 4.572 mm SLW socket-body height
= 7.072 mm nominal J1 stack
+ J1_SEATING_GAP_MM (0.000 mm default)
= 7.072 mm adapter-PCB underside height
```

The adapter top surface is nominally **7.872 mm** above the Compute Blade PCB because the board is 0.8 mm thick. `J1_SEATING_GAP_MM` is deliberately separate and defaults to `0.0`; it must not be folded into the nominal stack.

### Explicit modeling assumptions

At the required 3.40 mm insertion, the simplified model leaves **2.442 mm** axial clearance between the DDA socket body and the TSW body/elbow keepout. This passes the repository's conservative box-model check. Because the exact configured TSW CAD and the DDA socket-body solid are not present, exact TSW plastic/elbow interaction at 3.40 mm insertion still requires physical confirmation; the positive simplified clearance is not a claim of exact full-mating validation.

The DDA model treats the GNSS-side envelope as facing the mating plane and the battery/RTC envelope as facing away in the selected assembly. Both are conservative full-face boxes. Pin numbering remains a separate electrical concern.

## Official reference CAD and geometry validation

`scripts/fetch_reference_cad.py` downloads and authenticates upstream Compute Blade CAD at immutable commit [`9c7e472f4fb5c74401d17cdc7a766254d78a32c6`](https://github.com/uptime-lab/compute-blade/commit/9c7e472f4fb5c74401d17cdc7a766254d78a32c6):

- `models/blade/v1.0-mk4/v1.0_mk4_DEV.step`
- `models/bladerunner/19-inch/half body.stl`
- `models/bladerunner/19-inch/left bracket.stl`
- `models/bladerunner/19-inch/right bracket.stl`

The files are downloaded into ignored `mechanical/reference/` storage. The validator parses J3's actual placement from the official STEP: origin `(133.075077, 18.325065, 0.0)` mm and +X along the blade long axis. It also extracts the `Board` product's exact B-Rep bounds instead of substituting an assumed rectangle. Simplified adapter/DDA coordinates are transformed into and reported in this J3-anchored frame. The measured 2.5 mm plastic height and 9.0 mm pin-tip height are hard constraints rather than values inferred from tessellation.

This remains conservative box/mesh validation, not full B-Rep interference analysis. It authenticates the STEP and BladeRunner meshes, checks the J3 anchor/direction, measured header stack, SLW insertion minimum, the 3.40 mm J2 engagement requirement, 2.442 mm post margin, simplified body/elbow separation, confirmed pin-1 orientation, +Y placement, exact-PCB XY containment with margin, nearby-component keepouts, DDA socket-to-PCB offset, and BladeRunner Y/Z envelope. It also enforces a 36.0 mm maximum assembled Z-depth regression limit so a wrong-axis transform cannot silently return. The corrected selected orientation passes these simplified checks.

For the selected state, validation reports the full assembly (excluding the optional BladeRunner clearance frame) at X `−0.500..250.016` mm, Y `0.006..42.505` mm, and Z `−5.900..28.892` mm in the official STEP frame. Those spans are approximately 250.516 × 42.499 × 34.792 mm; total Z depth is **34.792 mm**.

## Inspecting the assembled 3D model

`scripts/generate_assembly_model.py` produces an inspectable, flattened multi-solid assembly at `mechanical/generated/full_assembly.step`. It imports the exact pinned official Compute Blade DEV B-Rep, derives the 0.8 mm adapter PCB outline and connector holes from the generated KiCad board, places J1/J2 from the validated board/configuration coordinates, and places the confirmed-orientation DDA at exactly 3.40 mm insertion. It imports the same axis-derived basis and +Y mating state used by `validate_geometry.py` and `mechanical_geometry.py`; it has no independent “looks right” placement.

The STEP is deliberately exported as a flat compound rather than a CadQuery hierarchical assembly. Some lightweight STEP viewers, including several VS Code extensions, show the hierarchical form as an empty scene even though OCCT/FreeCAD can reopen all of its solids. CI reopens the flattened file, checks its solid count and X/Y/Z bounds, and fails if geometry was lost. `full_assembly_lightweight.step` is also provided: it replaces the highly detailed official Compute Blade B-Rep with its validated PCB envelope while retaining the adapter, connector, pin, and DDA geometry. Use that file when a viewer cannot comfortably display the roughly 100 MB exact-blade assembly.

The assembly geometry distinguishes:

- gray: exact official Compute Blade geometry;
- green: actual adapter outline/holes and simplified measured DDA PCB;
- black: approximate connector/socket plastic;
- gold: dimension-driven pins and simplified bent tails;
- red: confirmed DDA physical pin 1;
- magenta/yellow: J1 and J2 +Y mating-axis markers.

J1 and J2 are dimension-driven approximations using the SLW/TSW manufacturer dimensions plus the actual KiCad pad positions. Exact configured Samtec STEP downloads are not available for deterministic unauthenticated CI use. The DDA is the existing measured simplified model. The adapter model represents board outline, holes, and thickness; copper and cosmetic board details are intentionally omitted because they do not change the mechanical stack.

`mechanical/generated/full_assembly_with_bladerunner.step` adds the exact J3-relative BladeRunner clearance frame used by validation. It does **not** apply an invented transform to the upstream BladeRunner STL: the official STL and Compute Blade STEP do not expose a shared installed-assembly datum in this repository. The gray frame is therefore an explicit clearance-envelope approximation, not the exact chassis solid.

Ten fixed-view renders are generated alongside the STEP files. They use a deterministic software projection of the same shared adapter, connector, pin, and DDA solids plus the official Compute Blade PCB bounds. This avoids driver-dependent blank OpenGL/VTK framebuffers in headless CI. The renderer and an independent verifier both require meaningful foreground area and pixel variation, so blank PNGs fail the workflow. The first three are explicit orientation inspections:

- `render_top.png`: +Z camera looking along −Z; the DDA PCB is edge-on near the +Y edge and J2 points +Y;
- `render_end.png`: +X camera looking along −X; the DDA is vertical and J2 rows stack in Z;
- `render_side.png`: +Y camera looking along −Y; the DDA PCB face is visible;
- `render_iso.png` provides the overall three-quarter view;
- `render_j1_closeup.png` for the Compute Blade header, J1 body, and adapter elevation;
- `render_j2_closeup.png` for the right-angle posts, 3.40 mm DDA socket position, upright DDA PCB, and body-clearance region.

The same four principal views are also emitted under the explicit revision names `assembly_top.png`, `assembly_x_view.png`, `assembly_y_view.png`, and `assembly_iso.png`.

Open the STEP files in FreeCAD or another multi-solid STEP viewer. On a successful workflow run, download `compute-blade-dda-adapter-reports`; it contains the two exact-blade flattened assemblies, the lightweight assembly, all ten renders, and `full_assembly_manifest.json` with the exact parameters, provenance, bounds, render-content metrics, and round-trip verification results. The large STEP files are generated in CI rather than committed.

The visual assembly is an inspection aid. It does not replace the physical connector and BladeRunner fit-check prototype.

## Regeneration and CI

```sh
python3 scripts/fetch_reference_cad.py
python3 scripts/generate_schematic.py
python3 scripts/generate_or_update_pcb.py
python3 scripts/generate_mechanical_model.py
python3 scripts/verify_connectivity.py
python3 scripts/validate_geometry.py --compare-variants
python3 -m unittest discover -s scripts -p 'test_*.py' -v
python3 -m pip install --requirement requirements-assembly.txt
python3 scripts/generate_assembly_model.py
```

`.github/workflows/pcb-ci.yml` runs those deterministic generation, unit, connectivity, and geometry checks on push, pull request, and manual dispatch. It then uses KiCad 10.0.5 for ERC, error-gated DRC, schematic/board views, Gerbers, and Excellon drills. No failure is hidden. Download `compute-blade-dda-adapter-manufacturing` from a workflow run for the Gerber ZIP and `compute-blade-dda-adapter-reports` for reports and renders.

The deterministic board embeds connector drawings while retaining official KiCad library IDs and pad geometry. The all-severity DRC report records two non-fatal `lib_footprint_mismatch` warnings; the error-only DRC gate must remain clean.

## Remaining unresolved mechanical items

- Whether the SLW socket physically bottoms against the Compute Blade header plastic exactly as modeled (`J1_SEATING_GAP_MM = 0.0`).
- Whether exact TSW plastic/elbow geometry permits at least 3.40 mm DDA insertion.
- Residual approximation between the parsed STEP J3 placement and the real extension-header mating datum/nearby detailed B-Rep surfaces.
- Actual installed 19-inch BladeRunner clearance beyond the authenticated mesh bounds and conservative envelope.
- A final physical fit-check prototype before ordering multiple boards.

The DDA pin-1 orientation, Compute Blade header heights, exposed-post length, and 7.072 mm nominal J1 stack are confirmed inputs and are no longer unresolved. This board is **not yet fabrication-ready** because the remaining connector-body and chassis-fit items above have not all been validated from exact CAD or physical assembly.
