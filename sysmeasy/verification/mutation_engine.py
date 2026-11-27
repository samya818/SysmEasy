"""Mutation engine: 15 calibration + 15 hold-out mutants for formal oracle validation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class Mutant:
    """A single mutant: a named transformation applied to a valid SysML v2 source."""

    mutant_id: str
    description: str
    is_hold_out: bool
    transform: Callable[[str], str]

    def apply(self, source: str) -> str:
        return self.transform(source)


def _replace_once(source: str, old: str, new: str) -> str:
    return source.replace(old, new, 1)


# ---------------------------------------------------------------------------
# 15 Calibration mutants  (used to tune oracle thresholds)
# ---------------------------------------------------------------------------
CALIBRATION_MUTANTS: list[Mutant] = [
    Mutant("MUT-01", "Zero out LiDAR power_w", False,
           lambda s: _replace_once(s, "attribute power_w : Real = 15.0;", "attribute power_w : Real = 0.0;")),
    Mutant("MUT-02", "Triple LocomotionSubsystem power (280 -> 840 W)", False,
           lambda s: _replace_once(s, "attribute power_w : Real = 280.0;", "attribute power_w : Real = 840.0;")),
    Mutant("MUT-03", "Remove REQ-01 requirement def block", False,
           lambda s: _remove_block(s, "requirement def 'REQ-01'")),
    Mutant("MUT-04", "Remove REQ-03 requirement def block", False,
           lambda s: _remove_block(s, "requirement def 'REQ-03'")),
    Mutant("MUT-05", "Drop LidarSensor part def", False,
           lambda s: _remove_block(s, "part def LidarSensor")),
    Mutant("MUT-06", "Change NavigationComputer port direction out->in", False,
           lambda s: s.replace("out port telemetry_out", "in port telemetry_out", 1)),
    Mutant("MUT-07", "Set ChassisStructure mass_kg to 0.0", False,
           lambda s: _replace_once(s, "attribute mass_kg : Real = 8.5;", "attribute mass_kg : Real = 0.0;")),
    Mutant("MUT-08", "Drop PowerSubsystem part def", False,
           lambda s: _remove_block(s, "part def PowerSubsystem")),
    Mutant("MUT-09", "Set all power_w values to 0 (blanket)", False,
           lambda s: _zero_all_power(s)),
    Mutant("MUT-10", "Remove package root declaration", False,
           lambda s: _replace_once(s, "package '", "namespace '")),
    Mutant("MUT-11", "Duplicate REQ-01 to introduce naming conflict", False,
           lambda s: s + "\n    requirement def 'REQ-01' { attribute targetValue : Real = 999.0; }\n"),
    Mutant("MUT-12", "Corrupt LidarSensor category to empty string", False,
           lambda s: _replace_once(s, 'attribute category : String = "sensor";', 'attribute category : String = "";')),
    Mutant("MUT-13", "Swap mass_kg and power_w values on NavigationComputer", False,
           lambda s: _swap_mass_power(s, "NavigationComputer", 0.95, 45.0)),
    Mutant("MUT-14", "Remove all port definitions from LocomotionSubsystem", False,
           lambda s: _remove_ports_from(s, "LocomotionSubsystem")),
    Mutant("MUT-15", "Set LidarSensor mass_kg to negative value", False,
           lambda s: _replace_once(s, "attribute mass_kg : Real = 0.83;", "attribute mass_kg : Real = -0.83;")),
]

# ---------------------------------------------------------------------------
# 15 Hold-out mutants  (kept unseen from calibration; generated independently)
# ---------------------------------------------------------------------------
HOLD_OUT_MUTANTS: list[Mutant] = [
    Mutant("HO-01", "Zero power on all actuators", True,
           lambda s: _zero_category_power(s, "actuator")),
    Mutant("HO-02", "Remove REQ-02 block", True,
           lambda s: _remove_block(s, "requirement def 'REQ-02'")),
    Mutant("HO-03", "Remove REQ-04 block", True,
           lambda s: _remove_block(s, "requirement def 'REQ-04'")),
    Mutant("HO-04", "Drop CablingAndFixings part def", True,
           lambda s: _remove_block(s, "part def CablingAndFixings")),
    Mutant("HO-05", "Set NavigationComputer power_w to 0.0", True,
           lambda s: _replace_once(s, "attribute power_w : Real = 45.0;", "attribute power_w : Real = 0.0;")),
    Mutant("HO-06", "Remove package entirely (replace with nothing)", True,
           lambda s: ""),
    Mutant("HO-07", "Inflate ChassisStructure mass_kg to 50.0 kg", True,
           lambda s: _replace_once(s, "attribute mass_kg : Real = 8.5;", "attribute mass_kg : Real = 50.0;")),
    Mutant("HO-08", "Rename PowerSubsystem to EnergyUnit", True,
           lambda s: s.replace("PowerSubsystem", "EnergyUnit")),
    Mutant("HO-09", "Change bus domain electrical->mechanical on all ports", True,
           lambda s: s.replace(": electrical;", ": mechanical;")),
    Mutant("HO-10", "Remove SystemAssembly block", True,
           lambda s: _remove_block(s, "part def SystemAssembly")),
    Mutant("HO-11", "Set LocomotionSubsystem mass_kg to 0.0", True,
           lambda s: _replace_once(s, "attribute mass_kg : Real = 2.48;", "attribute mass_kg : Real = 0.0;")),
    Mutant("HO-12", "Drop all requirement def blocks", True,
           lambda s: _drop_all_requirements(s)),
    Mutant("HO-13", "Set NavigationComputer mass_kg to 10.0 kg", True,
           lambda s: _replace_once(s, "attribute mass_kg : Real = 0.95;", "attribute mass_kg : Real = 10.0;")),
    Mutant("HO-14", "Remove LidarSensor power_in_24v port", True,
           lambda s: _remove_port_from_component(s, "LidarSensor", "power_in_24v")),
    Mutant("HO-15", "Change all comparators in requirements from >= to <=", True,
           lambda s: s.replace('attribute comparator : String = ">=";', 'attribute comparator : String = "<=";')),
]

ALL_MUTANTS = CALIBRATION_MUTANTS + HOLD_OUT_MUTANTS


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------
def _remove_block(source: str, keyword: str) -> str:
    """Remove the first {...} block whose line starts with keyword."""
    lines = source.splitlines(keepends=True)
    result = []
    skip = False
    depth = 0
    for line in lines:
        stripped = line.strip()
        if not skip and stripped.startswith(keyword):
            skip = True
            depth = line.count("{") - line.count("}")
            if depth <= 0:
                skip = False
            continue
        if skip:
            depth += line.count("{") - line.count("}")
            if depth <= 0:
                skip = False
            continue
        result.append(line)
    return "".join(result)


def _zero_all_power(source: str) -> str:
    import re
    return re.sub(r"attribute power_w : Real = [0-9]+(?:\.[0-9]+)?;",
                  "attribute power_w : Real = 0.0;", source)


def _zero_category_power(source: str, category: str) -> str:
    import re
    if f'attribute category : String = "{category}";' not in source:
        return source
    return re.sub(
        rf'(attribute category : String = "{category}";[^\}}]*?)attribute power_w : Real = [0-9]+(?:\.[0-9]+)?;',
        r"\1attribute power_w : Real = 0.0;",
        source, flags=re.DOTALL,
    )


def _swap_mass_power(source: str, name: str, mass: float, power: float) -> str:
    return (source
            .replace(f"attribute mass_kg : Real = {mass};", f"attribute mass_kg : Real = {power};", 1)
            .replace(f"attribute power_w : Real = {power};", f"attribute power_w : Real = {mass};", 1))


def _remove_ports_from(source: str, component: str) -> str:
    import re
    pattern = rf"(part def {component}\s*\{{)(.*?)(\}})"
    def _strip_ports(m):
        body = re.sub(r"\s+(in|out|inout)\s+port\s+\w+\s*:\s*\w+\s*;", "", m.group(2))
        return m.group(1) + body + m.group(3)
    return re.sub(pattern, _strip_ports, source, flags=re.DOTALL)


def _remove_port_from_component(source: str, component: str, port_name: str) -> str:
    import re
    pattern = rf"(part def {component}\s*\{{)(.*?)(\}})"
    def _strip(m):
        body = re.sub(rf"\s+(in|out|inout)\s+port\s+{port_name}\s*:\s*\w+\s*;", "", m.group(2))
        return m.group(1) + body + m.group(3)
    return re.sub(pattern, _strip, source, flags=re.DOTALL)


def _drop_all_requirements(source: str) -> str:
    import re
    return re.sub(r"\s+requirement def '[^']+' \{[^\}]*\}", "", source)
