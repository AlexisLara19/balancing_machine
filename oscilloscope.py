from __future__ import annotations

import numpy as np
import pyqtgraph as pg
from PyQt6.QtWidgets import QWidget, QVBoxLayout


class Oscilloscope(QWidget):
    HORIZONTAL_DIVISIONS = 10
    VERTICAL_DIVISIONS = 8

    def __init__(self):
        super().__init__()
        self.time_per_div = 0.010
        self.volts_per_div = 0.500
        self.vertical_center = 2.5

        self.plot = pg.PlotWidget()
        self.plot.setBackground('#101214')
        self.plot.showGrid(x=True, y=True, alpha=0.35)  # Grid
        self.plot.setLabel('bottom', 'Tiempo', units='s')  # Axis X
        self.plot.setLabel('left', 'Señal', units='V')  # Axis Y
        self.plot.addLegend()  # Title

        self.curve_vibration = self.plot.plot(name='Vibración', pen=pg.mkPen(pg.intColor(0, hues=2), width=2)) 
        self.curve_trigger = self.plot.plot(name='Trigger', pen=pg.mkPen(pg.intColor(1, hues=2), width=2))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.plot)
        self._apply_ranges()

    def set_time_per_div(self, seconds: float):
        self.time_per_div = max(1e-4, float(seconds))
        self._apply_ranges()

    def set_volts_per_div(self, volts: float):
        self.volts_per_div = max(1e-4, float(volts))
        self._apply_ranges()

    def set_vertical_center(self, volts: float):
        self.vertical_center = float(volts)
        self._apply_ranges()

    def visible_seconds(self) -> float:
        return self.HORIZONTAL_DIVISIONS * self.time_per_div

    def _apply_ranges(self):
        self.plot.setXRange(-self.visible_seconds(), 0.0, padding=0)
        half_span = self.VERTICAL_DIVISIONS * self.volts_per_div / 2.0
        self.plot.setYRange(self.vertical_center - half_span, self.vertical_center + half_span, padding=0)
        try:
            self.plot.getAxis('bottom').setTickSpacing(major=self.time_per_div, minor=self.time_per_div / 5.0)
            self.plot.getAxis('left').setTickSpacing(major=self.volts_per_div, minor=self.volts_per_div / 5.0)
        except Exception:
            pass

    def update_data(self, vibration_v: np.ndarray, trigger_v: np.ndarray, sample_rate: float):
        n = min(vibration_v.size, trigger_v.size)
        if n == 0 or sample_rate <= 0:
            return
        t = np.arange(n, dtype=np.float64) / sample_rate
        t -= t[-1]
        self.curve_vibration.setData(t, vibration_v[:n])
        self.curve_trigger.setData(t, trigger_v[:n])
