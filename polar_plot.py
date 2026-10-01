"""Polar 1X display; static reference grid and two dynamic items."""
from math import cos, sin, radians, isfinite
import numpy as np
import pyqtgraph as pg
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QDoubleSpinBox
from theme import COLORS


class PolarPlot(QWidget):
    def __init__(self):
        super().__init__()
        self._measurement = None
        layout = QVBoxLayout(self)
        controls = QHBoxLayout()
        controls.addWidget(QLabel('Escala radial máxima:'))
        self.radius_spin = QDoubleSpinBox()
        self.radius_spin.setDecimals(3)
        self.radius_spin.setRange(0.001, 100.0)
        self.radius_spin.setValue(1.0)
        self.radius_spin.setSingleStep(0.1)
        self.radius_spin.setSuffix(' V')
        controls.addWidget(self.radius_spin)
        controls.addStretch()
        layout.addLayout(controls)
        self.plot = pg.PlotWidget(background=COLORS['surface'])
        self.plot.setAspectLocked(True)
        self.plot.hideAxis('bottom')
        self.plot.hideAxis('left')
        self.plot.setMouseEnabled(x=False, y=False)
        self.plot.setMenuEnabled(False)
        layout.addWidget(self.plot, 1)
        self._grid = []
        self.vector = self.plot.plot(pen=pg.mkPen(COLORS['primary'], width=3))
        self.tip = self.plot.plot(pen=None, symbol='o', symbolSize=11,
                                  symbolBrush=COLORS['primary'], symbolPen='w')
        self.message = QLabel('Esperando datos con referencia de fase válida')
        self.message.setWordWrap(True)
        layout.addWidget(self.message)
        note = QLabel('0° a la derecha · sentido antihorario · trigger ascendente = 0°\n'
                      'Amplitud 1X en volts; no indica una masa de corrección.')
        note.setObjectName('subtitle')
        note.setWordWrap(True)
        layout.addWidget(note)
        self.radius_spin.valueChanged.connect(self._rebuild_grid)
        self._rebuild_grid()

    def _rebuild_grid(self, *_):
        for item in self._grid:
            self.plot.removeItem(item)
        self._grid.clear()
        radius = self.radius_spin.value()
        angles = np.linspace(0, 2 * np.pi, 181)
        for fraction in (0.25, 0.5, 0.75, 1.0):
            r = radius * fraction
            ring = self.plot.plot(r * np.cos(angles), r * np.sin(angles),
                                  pen=pg.mkPen(COLORS['border']))
            self._grid.append(ring)
            if fraction not in (0.5, 1.0):
                continue
            label = pg.TextItem(f'{r:g} V', color=COLORS['muted'], anchor=(0, 1))
            label.setPos(r * cos(radians(45)), r * sin(radians(45)))
            self.plot.addItem(label)
            self._grid.append(label)
        for degrees in range(0, 360, 90):
            a = radians(degrees)
            spoke = self.plot.plot([0, radius*cos(a)], [0, radius*sin(a)],
                                   pen=pg.mkPen(COLORS['border']))
            self._grid.append(spoke)
            label = pg.TextItem(f'{degrees}°', color=COLORS['heading'], anchor=(0.5, 0.5))
            label.setPos(1.12*radius*cos(a), 1.12*radius*sin(a))
            self.plot.addItem(label)
            self._grid.append(label)
        span = radius * 1.3
        self.plot.setRange(xRange=(-span, span), yRange=(-span, span), padding=0)
        self.update_measurement(self._measurement)

    def update_measurement(self, measurement):
        """measurement = (amplitude_volts, phase_degrees), or None when invalid."""
        self._measurement = measurement
        if measurement is None or not all(isfinite(v) for v in measurement) or measurement[0] <= 0:
            self.vector.setData([], [])
            self.tip.setData([], [])
            self.message.setText('Sin referencia de fase válida o sin amplitud 1X')
            return
        amplitude, phase = measurement
        a = radians(phase)
        self.vector.setData([0, amplitude*cos(a)], [0, amplitude*sin(a)])
        self.tip.setData([amplitude*cos(a)], [amplitude*sin(a)])
        suffix = ' · Fuera de escala: aumenta el máximo radial' if amplitude > self.radius_spin.value() else ''
        self.message.setText(f'Amplitud: {amplitude:.4f} V · Fase: {phase:.1f}°{suffix}')
