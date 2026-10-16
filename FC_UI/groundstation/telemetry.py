from __future__ import annotations

from dataclasses import dataclass
from theme import PALETTE
from enum import IntEnum

@dataclass(frozen=True)
class TelemetryFrame:
    # MCUTimer's physical value from the DBC, in seconds.
    mcu_time_s: float

    engine_thrust_n: float
    nitrous_weight_lbs: float
    run_tank_pressure_psi: float
    cc_pressure_psi: float
    top_cc_temp_c: float
    bot_cc_temp_c: float

    @property
    def t_seconds(self) -> float:
        """Convenience for the existing plotting interface."""
        return self.mcu_time_s

class SystemPhase(IntEnum):
    IDLE = 0
    INJECTOR_ARMED = 1
    INJECTOR_DISARMED = 2
    INJECTOR_FIRED = 3
    INJECTOR_FAULT = 4
    OPEN_SV11 = 5
    OPEN_SV12 = 6
    OPEN_SV13 = 7 
    CLOSE_SV11 = 8
    CLOSE_SV12 = 9
    CLOSE_SV13 = 10
    UNTESTED = 11
    SOFTWARE_CHECK_1 = 12
    HARDWARE_CHECK_2 = 13
    INTEGRATED_CHECK_3 = 14
    SENSORS_CHECK_4 = 15
    ALL_TESTED = 16
    MANUAL_PROCEED = 17

    @property
    def label(self) -> str:
        return _PHASE_LABELS[self]

    @property
    def color(self) -> str:
        return _PHASE_COLORS[self]

    @property
    def blurb(self) -> str:
        return _PHASE_BLURBS[self]

    @classmethod
    def from_value(cls, value: int) -> "SystemPhase":
        try:
            return cls(int(value))
        except (ValueError, TypeError):
            return cls.IDLE


_PHASE_LABELS = {
    SystemPhase.IDLE: "IDLE",
    SystemPhase.INJECTOR_ARMED: "INJECTOR_ARMED",
    SystemPhase.INJECTOR_DISARMED: "INJECTOR_DISARMED",
    SystemPhase.INJECTOR_FIRED: "INJECTOR_FIRED",
    SystemPhase.INJECTOR_FAULT: "INJECTOR_FAULT",
    SystemPhase.OPEN_SV11: "OPEN_SV11",
    SystemPhase.OPEN_SV12: "OPEN_SV12",
    SystemPhase.OPEN_SV13: "OPEN_SV13",
    SystemPhase.CLOSE_SV11: "CLOSE_SV11",
    SystemPhase.CLOSE_SV12: "CLOSE_SV12",
    SystemPhase.CLOSE_SV13: "CLOSE_SV13",
    SystemPhase.UNTESTED: "UNTESTED",
    SystemPhase.SOFTWARE_CHECK_1: "SOFTWARE_CHECK_1",
    SystemPhase.HARDWARE_CHECK_2: "HARDWARE_CHECK_2",
    SystemPhase.INTEGRATED_CHECK_3: "INTEGRATED_CHECK_3",
    SystemPhase.SENSORS_CHECK_4: "SENSORS_CHECK_4",
    SystemPhase.MANUAL_PROCEED: "MANUAL_PROCEED"
}

_PHASE_COLORS = {
    SystemPhase.IDLE: PALETTE.grey,
    SystemPhase.INJECTOR_ARMED: PALETTE.red,
    SystemPhase.INJECTOR_DISARMED: PALETTE.white,
    SystemPhase.INJECTOR_FIRED: PALETTE.amber,
    SystemPhase.INJECTOR_FAULT: PALETTE.magenta,
    SystemPhase.OPEN_SV11: PALETTE.amber,
    SystemPhase.OPEN_SV12: PALETTE.amber,
    SystemPhase.OPEN_SV13: PALETTE.amber,
    SystemPhase.CLOSE_SV11: PALETTE.white,
    SystemPhase.CLOSE_SV12: PALETTE.white,
    SystemPhase.CLOSE_SV13: PALETTE.white,
    SystemPhase.UNTESTED: PALETTE.grey,
    SystemPhase.SOFTWARE_CHECK_1: PALETTE.blue,
    SystemPhase.HARDWARE_CHECK_2: PALETTE.amber,
    SystemPhase.INTEGRATED_CHECK_3: PALETTE.navy,
    SystemPhase.SENSORS_CHECK_4: PALETTE.cyan,
    SystemPhase.ALL_TESTED: PALETTE.green,
    SystemPhase.MANUAL_PROCEED: PALETTE.navy_light
}

_PHASE_BLURBS = {
    SystemPhase.IDLE: "Idle state",
    SystemPhase.INJECTOR_ARMED: "The injecteor is armed and ready to be fired.",
    SystemPhase.INJECTOR_DISARMED: "The injector is disarmed, but all checks have been finished. it is ready to be armed.",
    SystemPhase.INJECTOR_FIRED: "The injector is currently being fired.",
    SystemPhase.INJECTOR_FAULT: "Fault state in case something is wrong with the injector.",
    SystemPhase.OPEN_SV11: "Opens the solenoid connecting the ground tank to the run tank.",
    SystemPhase.OPEN_SV12: "Opens the solenoid connected to the vent.",
    SystemPhase.OPEN_SV13: "Opens the solenoid connecting the run tank to the chamber.",
    SystemPhase.CLOSE_SV11: "Closes the solenoid connecting the ground tank to the run tank.",
    SystemPhase.CLOSE_SV12: "Closes the solenoid connected to the vent.",
    SystemPhase.CLOSE_SV13: "Closes the solenoid connecting the run tank to the chamber.",
    SystemPhase.UNTESTED: "No test has been made, or is currently being done.",
    SystemPhase.SOFTWARE_CHECK_1: "Software is currently being checked via a digital CAN frame being sent to the GUI for processing.",
    SystemPhase.HARDWARE_CHECK_2: "Hardware is currently being checked via sending signals from MCU >> board and back. Doesn't include sensors, and requires a manual proceed.",
    SystemPhase.INTEGRATED_CHECK_3: "The electronics and software are currently being tested by sending a frame from the MCU >> board >> GS for GUI processing.",
    SystemPhase.SENSORS_CHECK_4: "The sensors will send their current stream of data to the GUI.",
    SystemPhase.ALL_TESTED: "All systems have been tested and works properly.",
    SystemPhase.MANUAL_PROCEED: "The system requires a manual proceed to resume regular functions."
}
