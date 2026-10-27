# Third-party libraries

Some KiCad models come from vendor library services. Their terms do not clearly allow redistribution.
For that reason they are not in this repository. Download them yourself and place them at the paths below.
The KiCad projects find them through ${KIPRJMOD}.

| Part | Source | Files | Path in the project |
|---|---|---|---|
| ESP32-C3-DevKit-RUST-1 (PARTREV 1.2) | SnapEDA | STEP (used), symbol, footprint | hardware/shack-interface/lib/snapeda-devkit-rust-1/ and hardware/unit/controller-board/lib/snapeda-devkit-rust-1/ |
| TLP4176G photorelay | SamacSys (Component Search Engine) | STEP, saved as TLP4176G.stp | hardware/shack-interface/lib/3d/ and hardware/unit/controller-board/lib/3d/ |
| CPC1117N photorelay | SamacSys | STEP, saved as CPC1117N.stp | hardware/shack-interface/lib/3d/ |
| Same Sky MD-80SM mini-DIN 8 | SamacSys | STEP, saved as MD-80SM.stp | hardware/shack-interface/lib/3d/ |
| GCT USB4215-03-A USB-C | Ultra Librarian (via Digi-Key) | symbol, footprint (reference only) | hardware/shack-interface/lib/ultralibrarian-usb4215/ |
| Amass XT60PW-M, XT30PW-M | Amass / vendor STEP | STEP | hardware/unit/unit.3dshapes/ |
| Amphenol RF 83-1R (placeholder for 83-798) | Amphenol RF | STEP | hardware/unit/unit.3dshapes/ |
| TE RTD14012F relay (C-2-1419108-9) | TE Connectivity | STEP, saved as RTD14012F.step | hardware/unit/unit.3dshapes/ |
| Wurth 615008137121 RJ45 | Wurth Elektronik | STEP, saved as 615008137121.step | hardware/unit/controller-board/lib/3d/ |
| Amphenol FCI 54602-908LF RJ45 (filed for reference, not used since D-138) | Amphenol ICC | STEP, saved as 54602-908LF.step | hardware/unit/controller-board/lib/3d/ |
| Bourns 2036-xx-B2 GDT | Bourns (file 2036-XX-B2, 2012) | STEP, saved as Bourns_2036-xx-B2.stp | hardware/unit/controller-board/lib/3d/ |
| Samtec ESQ-112-33-G-D elevated socket (J2, D-139) | Samtec | STEP, saved as ESQ-112-33-G-D.stp | hardware/unit/controller-board/lib/3d/ |
| Samtec ESQ-112-37-G-D-LL elevated socket (not used, D-139) | Samtec | STEP, saved as ESQ-112-37-G-D-LL.stp | hardware/unit/controller-board/lib/3d/ |
| Samtec SLW-116-01-G-S low-profile socket (not used, D-140) | Samtec | STEP, saved as SLW-116-01-G-S.stp | hardware/unit/controller-board/lib/3d/ |
| Common-mode choke L1 to L4 (TDK ACT45B, D-149): KiCad library model L_CommonModeChoke_Coilcraft_1812CAN.step as a stand-in (same 1812 body) | KiCad library (CC-BY-SA 4.0 with exception) | STEP, referenced from the KiCad install (${KICAD10_3DMODEL_DIR}), not copied | – |

The footprints the boards use are drawn in this project (lib/*.pretty, rf-board.pretty). Only the 3D models depend on these files.
Without them the schematics and PCBs open and work. The 3D view shows the parts without a body.

The esp-rust-board library (hardware/shack-interface/lib/esp-rust-board/) is under CERN-OHL and stays in the repository.
