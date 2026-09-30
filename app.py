from __future__ import annotations

import serial.tools.list_ports
import numpy as np
from PyQt6.QtCore import Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox, QDoubleSpinBox, QFormLayout, QGridLayout, QGroupBox,
    QLabel, QMainWindow, QPushButton, QSpinBox, QWidget,
    QFrame, QHBoxLayout, QVBoxLayout, QScrollArea
)

from protocol import SAMPLES_PER_PACKET, ADC_BITS, ADC_MAX, SampleBlock
from buffer import DualChannelRingBuffer
from oscilloscope import Oscilloscope
from workers import SerialReader, SimulatorReader, ProtocolWorker
from analysis_worker import AnalysisWorker
from theme import stylesheet


class MainWindow(QMainWindow):
    protocol_reset = pyqtSignal()
    analysis_request = pyqtSignal(object, object, float, float, int)

    # Samples por segundo configuradas en el PSOC 4 (Clock)
    SAMPLE_RATE = 2000.0

    def __init__(self):
        super().__init__()
        self.setWindowTitle('Vibration Scope — PSoC 4')
        self.resize(1440, 900)
        self.setMinimumSize(1080, 720)
        self.setStyleSheet(stylesheet())

        self.buffer = DualChannelRingBuffer(capacity=200_000)
        self.source = None
        self.analysis_busy = False
        self.vref = 3.3  # Antes lo teniamos en 5V, pero VDDA es en realidad 3.3V

        self._build_workers()
        self._build_ui()

        self.render_timer = QTimer(self)
        self.render_timer.timeout.connect(self.refresh_plot)
        self.render_timer.start(33)  # aprox 30 FPS

        self.analysis_timer = QTimer(self)
        self.analysis_timer.timeout.connect(self.request_analysis)
        self.analysis_timer.start(100)  # aprox 10 análisis/s máximo

        self.port_timer = QTimer(self)
        self.port_timer.timeout.connect(self.refresh_ports)
        self.port_timer.start(1500)
        self.refresh_ports()

    def _build_workers(self):
        self.protocol_thread = QThread(self)
        self.protocol_worker = ProtocolWorker()
        self.protocol_worker.moveToThread(self.protocol_thread)
        self.protocol_worker.block_ready.connect(self.on_sample_block)
        self.protocol_worker.diagnostics.connect(self.on_protocol_diagnostics)
        self.protocol_reset.connect(self.protocol_worker.reset)
        self.protocol_thread.start()

        self.analysis_thread = QThread(self)
        self.analysis_worker = AnalysisWorker()
        self.analysis_worker.moveToThread(self.analysis_thread)
        self.analysis_request.connect(self.analysis_worker.analyze)
        self.analysis_worker.result_ready.connect(self.on_analysis_result)
        self.analysis_worker.error.connect(self.on_analysis_error)
        self.analysis_thread.start()

    def _build_ui(self):
        central = QWidget()
        central.setObjectName("workspace")
        self.setCentralWidget(central)
        root = QGridLayout(central)
        root.setColumnStretch(1, 1)
        root.setContentsMargins(24, 18, 24, 20)
        root.setHorizontalSpacing(20)
        root.setVerticalSpacing(16)
        root.setRowStretch(1, 1)
        header = QVBoxLayout()
        title = QLabel('Balanceadora')
        title.setObjectName('title')
        subtitle = QLabel('ADQUISICIÓN Y ANÁLISIS DE VIBRACIÓN  /  PSoC 4')
        subtitle.setObjectName('subtitle')
        header.addWidget(title)
        header.addWidget(subtitle)
        root.addLayout(header, 0, 0, 1, 2)
        self.metric_labels = {}
        content = QVBoxLayout()
        content.setSpacing(14)
        root.addLayout(content, 1, 1)
        highlights = QHBoxLayout()
        highlights.setSpacing(12)
        for key, title in [('rpm', 'VELOCIDAD · RPM'), ('one_x', 'AMPLITUD · 1X'), ('phase', 'FASE · 1X')]:
            card = QFrame()
            card.setObjectName('metricCard')
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(18, 14, 18, 14)
            caption = QLabel(title)
            caption.setObjectName('metricTitle')
            value = QLabel('—')
            value.setObjectName('metricValue')
            self.metric_labels[key] = value
            card_layout.addWidget(caption)
            card_layout.addWidget(value)
            highlights.addWidget(card, 1)
        content.addLayout(highlights)

        left = QWidget()
        left.setObjectName("controls")
        left_layout = QGridLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        sidebar = QScrollArea()
        sidebar.setWidgetResizable(True)
        sidebar.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        sidebar.setWidget(left)
        sidebar.setFixedWidth(350)
        root.addWidget(sidebar, 1, 0)

        connection_box = QGroupBox('Adquisición')
        connection = QFormLayout(connection_box)
        self.port_combo = QComboBox()
        self.baud_combo = QComboBox()
        self.baud_combo.addItems(['115200', '230400', '460800', '921600'])
        self.baud_combo.setCurrentText('115200')
        self.connect_btn = QPushButton('Conectar')
        self.connect_btn.clicked.connect(self.toggle_connection)
        self.status_label = QLabel('● Desconectado')
        self.status_label.setObjectName('status')
        self.status_label.setWordWrap(True)
        self.throughput_label = QLabel('0 B/s')
        connection.addRow('Fuente:', self.port_combo)
        connection.addRow('Baudrate:', self.baud_combo)
        connection.addRow(self.connect_btn)
        connection.addRow('Estado:', self.status_label)
        connection.addRow('Tráfico:', self.throughput_label)
        left_layout.addWidget(connection_box, 0, 0)

        acquisition_box = QGroupBox('Configuración de señal')
        acquisition = QFormLayout(acquisition_box)
        acquisition.addRow('Muestreo:', QLabel('2000 SPS / canal'))
        acquisition.addRow('ADC:', QLabel('12 bits, uint16'))
        acquisition.addRow('Paquete:', QLabel(f'{SAMPLES_PER_PACKET} muestras / canal'))

        self.vref_spin = QDoubleSpinBox()
        self.vref_spin.setRange(0.1, 20.0)
        self.vref_spin.setDecimals(3)
        self.vref_spin.setValue(self.vref)
        self.vref_spin.setSuffix(' V')
        self.vref_spin.valueChanged.connect(self.on_vref_changed)

        self.trigger_threshold = QSpinBox()
        self.trigger_threshold.setRange(0, ADC_MAX)
        self.trigger_threshold.setValue(2048)

        self.blades_spin = QSpinBox()
        self.blades_spin.setRange(1, 30)
        self.blades_spin.setValue(7)

        self.sim_rpm_spin = QDoubleSpinBox()
        self.sim_rpm_spin.setRange(60.0, 12000.0)
        self.sim_rpm_spin.setValue(1800.0)
        self.sim_rpm_spin.setSuffix(' RPM')
        self.sim_rpm_spin.valueChanged.connect(self.set_simulator_rpm)

        acquisition.addRow('ADC full-scale:', self.vref_spin)
        acquisition.addRow('Umbral trigger:', self.trigger_threshold)
        acquisition.addRow('N.º álabes:', self.blades_spin)
        acquisition.addRow('RPM simulador:', self.sim_rpm_spin)
        left_layout.addWidget(acquisition_box, 1, 0)

        scope_box = QGroupBox('Osciloscopio')
        scope_form = QFormLayout(scope_box)
        self.time_div_combo = QComboBox()
        self.time_div_values = [0.001, 0.002, 0.005, 0.010, 0.020, 0.050, 0.100, 0.200, 0.500]
        self.time_div_combo.addItems(['1 ms', '2 ms', '5 ms', '10 ms', '20 ms', '50 ms', '100 ms', '200 ms', '500 ms'])
        self.time_div_combo.setCurrentIndex(3)
        self.time_div_combo.currentIndexChanged.connect(self.change_time_div)

        self.volt_div_combo = QComboBox()
        self.volt_div_values = [0.050, 0.100, 0.200, 0.500, 1.0, 2.0]
        self.volt_div_combo.addItems(['50 mV', '100 mV', '200 mV', '500 mV', '1 V', '2 V'])
        self.volt_div_combo.setCurrentIndex(3)
        self.volt_div_combo.currentIndexChanged.connect(self.change_volt_div)

        scope_form.addRow('Tiempo/div:', self.time_div_combo)
        scope_form.addRow('Volt/div:', self.volt_div_combo)
        left_layout.addWidget(scope_box, 2, 0)

        analysis_box = QGroupBox('Análisis de balanceo')
        analysis = QFormLayout(analysis_box)
        metrics = [
            ('rot_hz', 'Frecuencia 1X'), ('rms', 'RMS AC'), ('p2p', 'Pico a pico'),
            ('crest', 'Factor de cresta'), ('dominant', 'Frecuencia dominante'),
            ('bpf', 'Paso de álabes (BPF)'), ('revs', 'Revoluciones analizadas'),
        ]
        for key, title in metrics:
            label = QLabel('—')
            label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.metric_labels[key] = label
            analysis.addRow(title + ':', label)


        diagnostics_box = QGroupBox('Protocolo')
        diagnostics = QFormLayout(diagnostics_box)
        self.protocol_label = QLabel('Paquetes 0 | CRC 0 | Bloques 0')
        self.protocol_label.setWordWrap(True)
        diagnostics.addRow(self.protocol_label)
        left_layout.addWidget(diagnostics_box, 3, 0)
        left_layout.setRowStretch(4, 1)

        self.scope = Oscilloscope()
        self.scope.set_time_per_div(self.time_div_values[self.time_div_combo.currentIndex()])
        self.scope.set_volts_per_div(self.volt_div_values[self.volt_div_combo.currentIndex()])
        self.scope.set_vertical_center(self.vref / 2.0)
        plot_box = QGroupBox('Señales en tiempo real')
        plot_layout = QVBoxLayout(plot_box)
        plot_layout.addWidget(self.scope)
        content.addWidget(plot_box, 1)
        content.addWidget(analysis_box)
        for form in (connection, acquisition, scope_form, analysis):
            form.setVerticalSpacing(10)
            form.setHorizontalSpacing(12)
            form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)

    def _set_status(self, text, state='idle'):
        self.status_label.setText(text)
        self.status_label.setProperty('state', state)
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)

    def refresh_ports(self):
        if self.source and self.source.isRunning():
            return
        current = self.port_combo.currentText()
        ports = [p.device for p in serial.tools.list_ports.comports()]
        options = ['SIMULATOR'] + ports
        self.port_combo.blockSignals(True)
        self.port_combo.clear()
        self.port_combo.addItems(options)
        if current in options:
            self.port_combo.setCurrentText(current)
        self.port_combo.blockSignals(False)

    def toggle_connection(self):
        if self.source and self.source.isRunning():
            self.stop_source()
        else:
            self.start_source()

    def start_source(self):
        name = self.port_combo.currentText()
        if not name:
            self.status_label.setText('● Sin fuente')
            return

        self.buffer.clear()
        self.protocol_reset.emit()

        if name == 'SIMULATOR':
            self.source = SimulatorReader(
                sample_rate=self.SAMPLE_RATE,
                rpm=self.sim_rpm_spin.value(),
                parent=self,
            )
        else:
            self.source = SerialReader(name, int(self.baud_combo.currentText()), parent=self)

        self.source.bytes_received.connect(self.protocol_worker.feed)
        self.source.connected.connect(self.on_connected)
        self.source.disconnected.connect(self.on_disconnected)
        self.source.throughput.connect(lambda b: self.throughput_label.setText(f'{b} B/s'))
        if hasattr(self.source, 'error'):
            self.source.error.connect(self.on_source_error)

        self.source.start()
        self.connect_btn.setText('Desconectar')

    def stop_source(self):
        if self.source:
            self.source.stop()
            self.source.wait(1500)
            self.source = None
        self.connect_btn.setText('Conectar')
        self._set_status('● Desconectado')

    def on_connected(self):
        self._set_status('● Conectado', 'connected')

    def on_disconnected(self):
        self._set_status('● Desconectado')
        self.connect_btn.setText('Conectar')

    def on_source_error(self, text):
        self._set_status(f'● Error: {text}', 'error')

    def on_sample_block(self, block: SampleBlock):
        self.buffer.append(block.vibration, block.trigger)

    def on_protocol_diagnostics(self, d: dict):
        self.protocol_label.setText(
            f"Paquetes OK {d.get('good_packets', 0)} | CRC {d.get('bad_crc', 0)} | "
            f"ADC {d.get('bad_adc', 0)} | Bloques {d.get('blocks', 0)} | "
            f"Seq perdidas {d.get('dropped_sequences', 0)}"
        )

    def counts_to_volts(self, data: np.ndarray) -> np.ndarray:
        return data.astype(np.float32) * (self.vref / ADC_MAX)

    def refresh_plot(self):
        visible_samples = max(2, int(np.ceil(self.scope.visible_seconds() * self.SAMPLE_RATE)))
        vibration, trigger = self.buffer.latest(visible_samples)
        if vibration.size == 0:
            return

        # print(
        #     "ADC CH0:",
        #     int(vibration[-1]),
        #     "Voltaje:",
        #     float(self.counts_to_volts(vibration[-1:])[0])
        # )

        raw = vibration[-1:]

        volts = self.counts_to_volts(raw)

        # print(
        #     f"CH0: ADC={int(vibration[-1])}, "
        #     f"V={float(self.counts_to_volts(vibration[-1:])[0]):.4f} | "
        #     f"CH1: ADC={int(trigger[-1])}, "
        #     f"V={float(self.counts_to_volts(trigger[-1:])[0]):.4f}"
        # )

        self.scope.update_data(
            self.counts_to_volts(vibration),
            self.counts_to_volts(trigger),
            self.SAMPLE_RATE,
        )

    def request_analysis(self):
        if self.analysis_busy:
            return
        # Hasta 2 segundos de señal para mejorar estabilidad de RPM/fase.
        n = int(self.SAMPLE_RATE * 2.0)
        vibration, trigger = self.buffer.latest(n)
        if vibration.size < SAMPLES_PER_PACKET:
            return
        self.analysis_busy = True
        self.analysis_request.emit(
            vibration, trigger, self.SAMPLE_RATE,
            float(self.trigger_threshold.value()), self.blades_spin.value()
        )

    def on_analysis_result(self, r: dict):
        self.analysis_busy = False
        if not r:
            return
        scale = self.vref / ADC_MAX
        self.metric_labels['rpm'].setText(f"{r['rpm']:.1f} RPM")
        self.metric_labels['rot_hz'].setText(f"{r['rot_hz']:.3f} Hz")
        self.metric_labels['one_x'].setText(f"{r['one_x_amp_counts'] * scale:.4f} V")
        self.metric_labels['phase'].setText(f"{r['phase_deg']:.1f}°")
        self.metric_labels['rms'].setText(f"{r['rms_counts'] * scale:.4f} V")
        self.metric_labels['p2p'].setText(f"{r['p2p_counts'] * scale:.4f} V")
        self.metric_labels['crest'].setText(f"{r['crest_factor']:.3f}")
        self.metric_labels['dominant'].setText(f"{r['dominant_hz']:.2f} Hz")
        self.metric_labels['bpf'].setText(f"{r['bpf_hz']:.2f} Hz")
        self.metric_labels['revs'].setText(str(r['revolutions']))

    def on_analysis_error(self, text):
        self.analysis_busy = False
        self._set_status(f'● Error análisis: {text}', 'error')

    def on_vref_changed(self, value):
        self.vref = float(value)
        self.scope.set_vertical_center(self.vref / 2.0)

    def change_time_div(self, index):
        self.scope.set_time_per_div(self.time_div_values[index])

    def change_volt_div(self, index):
        self.scope.set_volts_per_div(self.volt_div_values[index])

    def set_simulator_rpm(self, rpm):
        if isinstance(self.source, SimulatorReader):
            self.source.rpm = float(rpm)

    def closeEvent(self, event):
        self.stop_source()
        self.protocol_thread.quit()
        self.protocol_thread.wait(1000)
        self.analysis_thread.quit()
        self.analysis_thread.wait(1000)
        event.accept()
