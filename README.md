# HF Antenna Switch

A remote antenna switch for an amateur radio station.
It connects up to 3 HF radios to 4 antennas, with a path to 8 antennas.
The relay unit sits outdoors in a stainless steel (RVS) box. A small interface board in the shack controls it.

Status: design phase. Schematics are drawn and checked. No board is built yet. Nothing here is tested on the bench.

## About this project: designed with AI

This project has two goals.

1. Build a safe and useful antenna switch for my own station.
2. Find out how hardware design works when a person and an AI work on it together.

The second goal is the main reason the project exists.

The design is a joint effort between me (Prins Doornekamp) and an AI assistant, Claude by Anthropic.
I set the goals and the requirements. I took the decisions, often after the AI proposed and compared options.
The AI did much of the research, the calculations, the schematic generation scripts and the verification scripts.
Many ideas in this design came from the AI, and many were changed or rejected after discussion.
For that reason I do not claim this design as only my own work.

What this means for you as a reader:

- Values and calculations are checked by scripts and by review, but not all of them on the bench yet.
- The design log records who decided what, and why.
- See [docs/how-this-was-made.md](docs/how-this-was-made.md) for the method.

## What it does

- Connects each of 3 radios to a transmit antenna and, separately, to a receive antenna.
- Keeps receive-only antennas (such as a loop on ground) away from transmit power.
- Changes relays only when no RF is present (TX inhibit and handshake per radio).
- Stops all transmission and releases all relays on any fault, cable break or KILL switch.
- Grounds antennas that are not in use, through a static bleed.
- Feeds an active receive antenna through a switched bias-T.
- Is controlled from a computer over USB through the shack interface.

## Documents

| Document | Content |
|---|---|
| [docs/requirements.md](docs/requirements.md) | What we build and what is important |
| [docs/architecture.md](docs/architecture.md) | System blocks, interfaces, main decisions |
| [docs/design/](docs/design/) | Detailed design, one document per board |
| [docs/test/test-spec.md](docs/test/test-spec.md) | How each requirement is tested |
| [design-log.md](design-log.md) | Every decision, assumption, calculation, standard and measurement, with its reason |
| [CHANGELOG.md](CHANGELOG.md) | Changes per revision |

## Repository layout

```
docs/                 requirements, architecture, design, test
hardware/unit/        outdoor unit: RF board, controller board, case, verification scripts
hardware/shack-interface/   shack interface board
hardware/docs/diagrams/     logic, timing and flow diagrams
firmware/             box and shack firmware (not started)
tools/README.md       where each generator and verification script is, and how to run it
Datasheets/           datasheet register (PDFs are not in the repository)
archive/              earlier revisions (card cage and backplane, rev A/B)
```

## Tools

- KiCad 10
- Python 3 for the schematic generators and the verification scripts
- JLCPCB for the PCBs

## Licence

- Hardware design files and documentation: CERN Open Hardware Licence v2, Strongly Reciprocal (CERN-OHL-S-2.0). See [LICENSE](LICENSE).
- Python scripts (schematic generators, verification): MIT. See [LICENSE-MIT](LICENSE-MIT).
- Vendor 3D models and libraries (SnapEDA, SamacSys, Ultra Librarian, Amass, Amphenol) are not in the repository. See [hardware/THIRD-PARTY.md](hardware/THIRD-PARTY.md) for where to get them.

Source Location (required by CERN-OHL-S): https://github.com/PostbodeSiem/hf-antenna-switch
