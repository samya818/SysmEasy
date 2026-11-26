package 'Rover Tout-Terrain' {
    doc /* Contract CTR-ROV-2026-001 (v1.0) */

    private import ScalarValues::*;

    requirement def 'REQ-01' {
        doc /* Autonomie opérationnelle: Autonomie minimale en déplacement continu */
        attribute targetValue : Real = 90.0;
        attribute unit : String = "min";
        attribute comparator : String = ">=";
    }
    requirement def 'REQ-02' {
        doc /* Vitesse maximale: Vitesse de pointe sur sol meuble */
        attribute targetValue : Real = 1.5;
        attribute unit : String = "m/s";
        attribute comparator : String = "<=";
    }
    requirement def 'REQ-03' {
        doc /* Masse totale maximale: Masse totale en ordre de marche */
        attribute targetValue : Real = 25.0;
        attribute unit : String = "kg";
        attribute comparator : String = "<=";
    }
    requirement def 'REQ-04' {
        doc /* Tension de bus: Tension nominale du bus d alimentation CC */
        attribute targetValue : Real = 24.0;
        attribute unit : String = "V";
        attribute comparator : String = "==";
    }

    part def ChassisStructure {
        attribute category : String = "part";
        attribute mass_kg : Real = 8.5;
        attribute power_w : Real = 0.0;
    }
    part def LocomotionSubsystem {
        attribute category : String = "actuator";
        attribute mass_kg : Real = 2.48;
        attribute power_w : Real = 280.0;
        in port power_in_24v : electrical;
    }
    part def PowerSubsystem {
        attribute category : String = "part";
        attribute mass_kg : Real = 6.2;
        attribute power_w : Real = 0.0;
        out port power_out_24v : electrical;
    }
    part def NavigationComputer {
        attribute category : String = "controller";
        attribute mass_kg : Real = 0.95;
        attribute power_w : Real = 45.0;
        in port power_in_24v : electrical;
        out port telemetry_out : data;
    }
    part def LidarSensor {
        attribute category : String = "sensor";
        attribute mass_kg : Real = 0.83;
        attribute power_w : Real = 15.0;
        in port power_in_24v : electrical;
    }
    part def CablingAndFixings {
        attribute category : String = "part";
        attribute mass_kg : Real = 3.84;
        attribute power_w : Real = 0.0;
    }

    part def SystemAssembly {
        part chassisstructure : ChassisStructure;
        part locomotionsubsystem : LocomotionSubsystem;
        part powersubsystem : PowerSubsystem;
        part navigationcomputer : NavigationComputer;
        part lidarsensor : LidarSensor;
        part cablingandfixings : CablingAndFixings;
    }
}
