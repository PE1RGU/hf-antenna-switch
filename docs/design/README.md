# Detailed design

One document per board. Each document follows the same outline:

1. Function and interfaces (connectors, signals, power)
2. Circuit description per schematic sheet
3. Component selection and derating (reference to Datasheets/_register.md)
4. Calculations
5. Layout rules
6. Verification done (ERC, netlist checks, logic checks)
7. Open items

| Board | Document | KiCad project |
|---|---|---|
| RF board | [rf-board.md](rf-board.md) | hardware/unit/rf-board/ |
| Controller board | [controller-board.md](controller-board.md) | hardware/unit/controller-board/ |
| Case | [case.md](case.md) | hardware/unit/unit-case-sketch.svg |
| Shack interface | [shack-interface.md](shack-interface.md) | hardware/shack-interface/ |
