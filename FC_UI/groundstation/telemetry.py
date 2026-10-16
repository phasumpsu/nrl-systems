from __future__ import annotations

from dataclasses import dataclass
from groundstation.theme import PALETTE
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
    sv11_state: int
    sv12_state: int
    sv13_state: int
    ignitor_state: int

    @property
    def t_seconds(self) -> float:
        """Convenience for the existing plotting interface."""
        return self.mcu_time_s

class TestPhase(IntEnum):
    IDLE = 0
    UNTESTED = 1
    SOFTWARE_CHECK = 2
    HARDWARE_CHECK = 3
    INTEGRATED_CHECK = 4
    SENSORS_CHECK = 5
    ALL_TESTED = 6
    AWAITING_PROCEED = 7

    @property
    def label(self) -> str:
        return _TEST_DISPLAY_PHASE[self]

    @property
    def blurb(self) -> str:
        return _TEST_PHASE_BLURBS[self]

    @property
    def color(self) -> str:
        return _TEST_DISPLAY_COLORS[self]

class OperatorRequest(IntEnum):
    OPEN_SV11 = 1
    OPEN_SV12 = 2
    OPEN_SV13 = 3
    CLOSE_SV11 = 4
    CLOSE_SV12 = 5
    CLOSE_SV13 = 6
    MANUAL_PROCEED = 7
    CLOSE_GUI = 8

    @property
    def label(self) -> str:
        return _INTERACT_LABELS[self]

    @property
    def blurb(self) -> str:
        return _REQUEST_BLURBS[self]

    
class ObservedState(IntEnum):
    UNKNOWN = 0
    OPENED = 1
    CLOSED = 2
    FAULT = 3

    @property
    def label(self) -> str:
        return _OBSERVED_DISPLAY_PHASE[self]

    @property
    def color(self) -> str:
        return _OBSERVED_DISPLAY_COLORS[self]

    @property
    def blurb(self) -> str:
        return _OBSERVED_BLURBS[self]

_TEST_DISPLAY_PHASE = {
    TestPhase.IDLE: "IDLE",
    TestPhase.UNTESTED: "UNTESTED",
    TestPhase.SOFTWARE_CHECK: "SOFTWARE_CHECK",
    TestPhase.HARDWARE_CHECK: "HARDWARE_CHECK",
    TestPhase.INTEGRATED_CHECK: "INTEGRATED_CHECK",
    TestPhase.SENSORS_CHECK: "SENSORS_CHECK",
    TestPhase.ALL_TESTED: "ALL_TESTED",
    TestPhase.AWAITING_PROCEED: "AWAITING_PROCEED"
    }

_OBSERVED_DISPLAY_PHASE = {
    ObservedState.FAULT: "FAULT",
    ObservedState.OPENED: "OPENED",
    ObservedState.CLOSED: "CLOSED",
    ObservedState.UNKNOWN: "UNKNOWN",
    }

_INTERACT_LABELS = {
    OperatorRequest.OPEN_SV11: "OPEN_SV11",
    OperatorRequest.OPEN_SV12: "OPEN_SV12",
    OperatorRequest.OPEN_SV13: "OPEN_SV13",
    OperatorRequest.CLOSE_SV11: "CLOSE_SV11",
    OperatorRequest.CLOSE_SV12: "CLOSE_SV12",
    OperatorRequest.CLOSE_SV13: "CLOSE_SV13",
    OperatorRequest.MANUAL_PROCEED: "MANUAL_PROCEED",
    OperatorRequest.CLOSE_GUI: "CLOSE_GUI"
}

_TEST_DISPLAY_COLORS = {
    TestPhase.IDLE: PALETTE.grey,
    TestPhase.UNTESTED: PALETTE.grey,
    TestPhase.SOFTWARE_CHECK: PALETTE.blue,
    TestPhase.HARDWARE_CHECK: PALETTE.navy,
    TestPhase.INTEGRATED_CHECK: PALETTE.cyan,
    TestPhase.SENSORS_CHECK: PALETTE.white,
    TestPhase.ALL_TESTED: PALETTE.green,
    TestPhase.AWAITING_PROCEED: PALETTE.navy_light,
}

_OBSERVED_DISPLAY_COLORS = {
    ObservedState.FAULT: PALETTE.magenta,
    ObservedState.OPENED: PALETTE.amber,
    ObservedState.CLOSED: PALETTE.bg_deep,
    ObservedState.UNKNOWN: PALETTE.red
}


_TEST_PHASE_BLURBS = {
    TestPhase.IDLE: "Idle state",
    TestPhase.UNTESTED: "No test has been made, or is currently being done.",
    TestPhase.SOFTWARE_CHECK: "Software is currently being checked via a digital CAN frame being sent to the GUI for processing.",
    TestPhase.HARDWARE_CHECK: "Hardware is currently being checked via sending signals from MCU >> board and back. Doesn't include sensors, and requires a manual proceed.",
    TestPhase.INTEGRATED_CHECK: "The electronics and software are currently being tested by sending a frame from the MCU >> board >> GS for GUI processing.",
    TestPhase.SENSORS_CHECK: "The sensors will send their current stream of data to the GUI.",
    TestPhase.ALL_TESTED: "All systems have been tested and works properly.",
    TestPhase.AWAITING_PROCEED: "After tests have been completed, a separate proceed is required to resume regular functions.",
}

_REQUEST_BLURBS = {
    OperatorRequest.OPEN_SV11: "Opens the solenoid connecting the ground tank to the run tank.",
    OperatorRequest.OPEN_SV12: "Opens the solenoid connected to the vent.",
    OperatorRequest.OPEN_SV13: "Opens the solenoid connecting the run tank to the chamber.",
    OperatorRequest.CLOSE_SV11: "Closes the solenoid connecting the ground tank to the run tank.",
    OperatorRequest.CLOSE_SV12: "Closes the solenoid connected to the vent.",
    OperatorRequest.CLOSE_SV13: "Closes the solenoid connecting the run tank to the chamber.",
    OperatorRequest.MANUAL_PROCEED: "The system requires a manual proceed to resume regular functions.",
    OperatorRequest.CLOSE_GUI: "Requests the GUI to be closed. Will actually happen after all processes have properly shutdown."
}
_OBSERVED_BLURBS = {
    ObservedState.FAULT: "Fault state.",
    ObservedState.OPENED: "The solenoid is currently open.",
    ObservedState.CLOSED: "The solenoid is currently closed.",
    ObservedState.UNKNOWN: "The state of the solenoid is unknown."
}
