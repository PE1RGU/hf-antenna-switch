# Tools

This folder holds no scripts. The scripts stay next to the files they read and write. Each script runs from its own folder and uses relative paths only.

This page lists where each script is and how to run it. Paths are relative to the repository root.

Requirements: Python 3.10 or later. gen_diagrams.py also needs matplotlib. KiCad 10 opens the generated files. Licence of the scripts: MIT (LICENSE-MIT).

## Schematic generators

Each generator writes all schematic sheets, the project symbol library and the library tables of its board. The same input gives the same files (stable UUIDs).

| Script | Folder | Board | Reads |
|---|---|---|---|
| gen_rfboard_sch.py | hardware/unit/rf-board/ | RF board | _sym/ |
| gen_controller_sch.py | hardware/unit/controller-board/ | Controller board | _sym/ |
| gen_shack_sch.py | hardware/shack-interface/ | Shack interface | _sym/ |

```
cd hardware/unit/rf-board && python3 gen_rfboard_sch.py
cd hardware/unit/controller-board && python3 gen_controller_sch.py
cd hardware/shack-interface && python3 gen_shack_sch.py
```

After a run: run ERC in KiCad, export the netlist and run the verification scripts.

## Footprint generators

Folder: hardware/shack-interface/lib/. Run each script from that folder.

| Script | Footprint | Writes into |
|---|---|---|
| gen_photorelay_fp.py | SOP-4_P2.54mm_PhotoRelay_LongPad (D-99) | shack-interface.pretty/ and ../../unit/controller-board/lib/controller-board.pretty/ |
| gen_minidin_fp.py | MiniDIN-8_SameSky_MD-80SM_Horizontal (D-100) | shack-interface.pretty/ |
| gen_devkit_fp.py | ESP32-C3-DevKit-RUST_Socket (D-95) | shack-interface.pretty/ and ../../unit/controller-board/lib/controller-board.pretty/ |

The 3D models these footprints refer to are not in the repository. See hardware/THIRD-PARTY.md.

Controller board: `cd hardware/unit/controller-board/lib && python3 gen_ctl_fp.py` writes RJ45_8P8C_Unshielded_TabDown (D-138) and GDT_3Pin_Bourns_2036-B2_P4.40mm into controller-board.pretty/. `python3 gen_gdt_step.py` (needs cadquery) writes 3d/GDT_2036-B2.step.
RF board: `cd hardware/unit/rf-board && python3 gen_so239_fp.py` writes SO239_83-798_StrapPad_BossRight and _BossLeft into rf-board.pretty/ (D-105).
RF board: `cd hardware/unit/rf-board && python3 gen_rf_fp.py` writes SMA_901-9215_StrapPad, WireLink_P7.62mm_D1.0mm and GDT_Axial_P15.24mm into rf-board.pretty/ (D-109, D-110).
Controller board layout: `/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/3.9/bin/python3 gen_controller_pcb.py` in hardware/unit/controller-board/ makes controller-board.kicad_pcb new from the netlist (NETLIST in the script) and places all parts; coordinates in the RF board frame. Controller board routing (D-143, D-144), in hardware/unit/controller-board/routing/: (0) `gen_controller_pcb.py --no-routes` (board without the old tracks); (1) KiCad Python `export_geom.py` writes geom.json (pads, rule area, holes and the locked GND vias; routed tracks are left out); (2) `python3 grid_router.py` (numpy, scipy, numba; about 30 s; 4 layers, D-144) writes routes.json; (3) KiCad Python `../gen_controller_pcb.py` applies routes.json; (4) `kicad-cli pcb drc --refill-zones --save-board`. Run all four again after any placement change. Fixed fan-out copper (U13, D-154): gen_controller_pcb.py writes routing/terminals.json; export_geom.py moves those pads to their terminal, and the router ends there. RF board routing (p2c, M-75), in hardware/unit/rf-board/routing/: (0) KiCad Python `gen_rfboard_pcb.py --no-routes` in hardware/unit/rf-board/ (board without routes; also writes terminals.json for the fan-out vias, D-161); (1) KiCad Python `export_geom.py` writes geom.json (all copper on the board is fixed copper then); (2) `python3 grid_router.py router_cfg.json` (general router: layers, regions, RF clearances and classes in router_cfg.json; about 5 minutes per pass, 3 passes; it needs more than 180 s, so run it where a job can run longer than the device shell allows, for example the cloud workspace) writes routes.json; (3) KiCad Python `gen_rfboard_pcb.py` applies routes.json and removes fan-out vias the routes do not need; (3b) `python3 stitch.py router_cfg.json` writes stitch.json (edge fence, 5 mm grid, return-via report; gen_rfboard_pcb.py adds the vias with the routes); (4) `kicad-cli pcb drc --refill-zones --save-board`; (5) Claude outputs/pcbwork/rf/bends.py and netcheck.py <board> routing/routes.json. Aggressor/victim check: `python3 xtalk.py routes.json` in routing/ (victim and aggressor patterns in the script header). The router with return vias takes about 50 minutes (6 passes).
3D view of the stack: after a controller layout change run `kicad-cli pcb export step --force --subst-models --no-unspecified -o unit.3dshapes/controller-board.step controller-board/controller-board.kicad_pcb` in hardware/unit/, then gen_rfboard_pcb.py; the RF board 3D view shows the controller board on 20 mm standoffs (CTL3D). 3D fit: `kicad-cli pcb export step --subst-models` of both boards, then the cadquery check (Claude outputs/pcbwork/ctl/fit.py, not in Git yet).
RF board layout, in this order: (1) `python3 gen_rfboard_sch.py`; (2) netlist: `kicad-cli sch export netlist --format kicadxml -o ../verify/rf12.xml rf-board.kicad_sch` (new file name per schematic revision, then set NETLIST in gen_rfboard_pcb.py); (3) `/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/3.9/bin/python3 gen_rfboard_pcb.py` loads new or changed footprints from the libraries and sets the nets, values, outline, page (A3), stackup, netclasses and placement; (4) `kicad-cli pcb drc --severity-all --format json`. All layout work is in gen_rfboard_pcb.py.

Shack interface layout and routing (p3, M-89), in hardware/shack-interface/: (0) KiCad Python `gen_shack_pcb.py --no-routes` (netlist ../unit/verify/si15.xml; placement by templates, planes, plane vias, USB-C fan-out; writes routing/terminals.json and routing/keepout.json); (1) KiCad Python `routing/export_geom.py` writes geom.json; (2) `python3 grid_router.py router_cfg.json` in routing/ (general router with per-net keep-out areas from keepout.json; about 10 minutes, 4 passes; run it in the cloud workspace) writes routes.json; (3) KiCad Python `gen_shack_pcb.py` applies routes.json and adds the stitching vias; (4) `kicad-cli pcb drc --refill-zones --save-board --severity-all --format json -o drc.json shack-interface.kicad_pcb`. Placement check before routing: Claude outputs/pcbwork/shack/placement_dump.py and airwire_render.py (`--supply GND,+3V3,+5V,+13V8,CHASSIS,RGND`).

Shack interface end plates (D-179), in hardware/shack-interface/endplates/: KiCad Python `gen_endplates.py` writes rear-panel.kicad_pcb and front-panel.kicad_pcb from the connector positions on ../shack-interface.kicad_pcb; then `kicad-cli pcb drc --refill-zones --save-board` per plate and `kicad-cli pcb render --use-board-stackup-colors` for the view.

## Drawings and diagrams

| Script | Folder | Output |
|---|---|---|
| gen_relay_placement.py | hardware/unit/ | relay-placement-study.svg (also checks the clearance of the board supports, D-102) |
| gen_case_sketch.py | hardware/unit/ | unit-case-sketch.svg |
| gen_diagrams.py | hardware/docs/diagrams/ | L1 to L3, T1 to T4, F1, F2 as SVG and PNG |

## Verification

Folder: hardware/unit/verify/. The netlists in this folder are inputs and stay in the repository.

| Script | Inputs (default) | Report |
|---|---|---|
| verify_logic.py | rf12.xml (RF board), ctl11.xml (controller board) | logic-verification.md |
| verify_system.py | si14.xml (shack interface), ctl11.xml (controller board) | system-verification.md |
| nl.py | – | helper: reads a KiCad XML netlist |

```
cd hardware/unit/verify
python3 verify_logic.py rf12.xml ctl11.xml
python3 verify_system.py si14.xml ctl11.xml
```

Without arguments the scripts use the netlists in the table. The scripts print the report; redirect it into the report file (for example `python3 verify_logic.py > logic-verification.md`). Exit code 0 means all checks pass. After a schematic change, export new netlists into this folder and give their names as arguments.

## Netlist comparison (one-off)

These scripts compared a netlist with an earlier revision after a redraw. They map the changed pin numbers of that redraw, so they are for the record only.

| Script | Folder | Use |
|---|---|---|
| netcmp3.py | hardware/shack-interface/ | a6 against a7 (M-22, M-23) |
| netcmp-c4.py | hardware/unit/controller-board/ | c3 against c4 (M-23) |

## Fabrication files (JLCPCB)

Fabrication Toolkit (KiCad plugin, bennymeg), from the command line on the Mac (zones filled first with kicad-cli pcb drc --refill-zones --save-board):
`cd ~/Documents/KiCad/10.0/3rdparty/plugins && /Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/3.9/bin/python3 -m com_github_bennymeg_JLC-Plugin-for-KiCad.cli -p <board>.kicad_pcb -e -nI -nB`
Output in production/ next to the board. Do not pass -aN (the archive name needs the GUI board) or -f (zone fill through the SWIG backend).
Hand-assembly BOM: `python3 gen_bom.py` in hardware/unit/controller-board/ (production/bom_hand_assembly.csv).
