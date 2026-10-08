"""Operator workflow for one-plane balancing; live acquisition stays in MainWindow."""
import json
import time
from pathlib import Path
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QFormLayout,
    QLabel, QPushButton, QDoubleSpinBox, QComboBox, QLineEdit, QGroupBox,
    QFileDialog, QBoxLayout)
from calibration_core import Calibration, summarize, calibrate, correction, distribute_on_blades
from protocol import ADC_MAX


class BalancingPanel(QWidget):
    WINDOW_SAMPLES = 4000
    CAPTURE_WINDOWS = 3

    def __init__(self, window):
        super().__init__()
        self.setObjectName("balancingPanel")
        self.window = window
        self.calibration = None
        self.initial = self.trial = self.test = self.residual = None
        self.pending = None
        self.saved_path = None
        self._loading = False
        root = QVBoxLayout(self)
        top = QHBoxLayout()
        top.addWidget(QLabel('Calibración · un plano'))
        self.load_btn = QPushButton('Cargar calibración')
        self.load_btn.clicked.connect(self.load_calibration)
        top.addWidget(self.load_btn)
        root.addLayout(top)
        self.summary = QLabel('Sin calibración. Carga un archivo o crea una calibración.')
        self.summary.setWordWrap(True)
        root.addWidget(self.summary)
        root.addWidget(self._calibration_page())
        self.message = QLabel('Completa la configuración y captura sin/con masa de prueba.')
        self.message.setWordWrap(True)
        self.message.setObjectName('status')
        root.addWidget(self.message)
        self.cancel_btn = self.button('Cancelar captura', lambda: self.cancel_capture('Captura cancelada.'))
        root.addWidget(self.cancel_btn)
        root.addStretch()

        self.test_widget = QWidget()
        self.test_widget.setObjectName('balancePage')
        test_layout = QVBoxLayout(self.test_widget)
        test_header = QHBoxLayout()
        test_header.addWidget(QLabel('Prueba de balanceo · un plano'))
        self.test_load_btn = self.button('Cargar calibración', self.load_calibration)
        test_header.addWidget(self.test_load_btn)
        test_layout.addLayout(test_header)
        self.test_summary = QLabel(self.summary.text())
        self.test_summary.setWordWrap(True)
        test_layout.addWidget(self.test_summary)
        test_layout.addWidget(self._test_page())
        self.test_message = QLabel('Selecciona una calibración y conecta la fuente para medir.')
        self.test_message.setWordWrap(True)
        self.test_message.setObjectName('status')
        test_layout.addWidget(self.test_message)
        self.test_cancel_btn = self.button('Cancelar captura', lambda: self.cancel_capture('Captura cancelada.'))
        test_layout.addWidget(self.test_cancel_btn)
        test_layout.addStretch()
        self.settings_widgets = [self.profile, self.reference, self.direction, self.phase_sign,
                                 self.rpm, self.tolerance, self.stability, self.mass, self.radius, self.angle]
        for widget in self.settings_widgets:
            if isinstance(widget, QLineEdit):
                widget.textChanged.connect(self._settings_changed)
            elif isinstance(widget, QComboBox):
                widget.currentIndexChanged.connect(self._settings_changed)
            else:
                widget.valueChanged.connect(self._settings_changed)
        self.correction_radius.valueChanged.connect(self._show_test)
        self.limit.valueChanged.connect(self._show_test)
        self.blade_one.valueChanged.connect(self._show_test)
        self.window.blades_spin.valueChanged.connect(self._show_test)
        self._buttons()
        self.set_compact(window.width() < 1300)

    def set_compact(self, compact):
        self.calibration_columns.setDirection(QBoxLayout.Direction.TopToBottom if compact else QBoxLayout.Direction.LeftToRight)

    @staticmethod
    def spin(low, high, value, suffix, decimals=2):
        w = QDoubleSpinBox()
        w.setDecimals(decimals); w.setRange(low, high); w.setValue(value); w.setSuffix(suffix)
        return w

    @staticmethod
    def button(text, callback):
        w = QPushButton(text); w.clicked.connect(callback); return w

    def _calibration_page(self):
        page = QWidget(); page.setObjectName("balancePage"); layout = QVBoxLayout(page)
        columns = QBoxLayout(QBoxLayout.Direction.TopToBottom)
        self.calibration_columns = columns
        layout.addLayout(columns)
        box = QGroupBox('Configuración · un plano'); form = QFormLayout(box)
        self.profile = QLineEdit(); self.profile.setPlaceholderText('Ej. ventilador A / montaje 1')
        self.reference = QLineEdit(); self.reference.setPlaceholderText('Ej. marca del cubo = 0°')
        self.direction = QComboBox(); self.direction.addItems(['Horario', 'Antihorario'])
        self.phase_sign = QComboBox(); self.phase_sign.addItems(['Fase aumenta con el ángulo (+)', 'Fase disminuye con el ángulo (−)'])
        self.phase_sign.setToolTip('Validar físicamente moviendo una masa conocida. Una sola posición no determina este signo.')
        self.rpm = self.spin(60, 12000, 1800, ' RPM', 1)
        self.tolerance = self.spin(.1, 10, 2, ' %')
        self.stability = self.spin(.1, 50, 10, ' %')
        for title, w in [('Perfil / montaje:',self.profile), ('Referencia 0°:',self.reference),
            ('Ángulos físicos:',self.direction), ('Respuesta angular:',self.phase_sign),
            ('Velocidad nominal:',self.rpm), ('Tolerancia RPM:',self.tolerance), ('Variación vectorial máx.:',self.stability)]:
            form.addRow(title, w)
        columns.addWidget(box, 1)
        right = QVBoxLayout(); columns.addLayout(right, 1)
        box = QGroupBox('Masa de prueba'); form = QFormLayout(box)
        self.mass = self.spin(.001, 10000, 1, ' g', 3)
        self.radius = self.spin(.1, 10000, 100, ' mm')
        self.angle = self.spin(0, 359.99, 0, '°')
        form.addRow('Masa:',self.mass);form.addRow('Radio:',self.radius);form.addRow('Ángulo desde 0°:',self.angle)
        note = QLabel('Define la marca de 0° y valida el signo angular con una masa conocida antes de usar los ángulos de corrección.')
        note.setWordWrap(True);form.addRow(note); right.addWidget(box)
        self.initial_btn = self.button('1. Capturar sin masa de prueba', lambda: self.begin_capture('initial'))
        self.trial_btn = self.button('2. Capturar con masa de prueba', lambda: self.begin_capture('trial'))
        right.addWidget(self.initial_btn)
        self.initial_label = QLabel('Inicial: —'); right.addWidget(self.initial_label)
        right.addWidget(self.trial_btn)
        self.trial_label = QLabel('Con masa de prueba: —'); right.addWidget(self.trial_label)
        self.save_btn = self.button('3. Calcular y guardar calibración', self.save_calibration)
        right.addWidget(self.save_btn)
        note = QLabel('Detén el rotor para colocar la masa de prueba. Retírala al terminar la calibración.')
        note.setWordWrap(True);layout.addWidget(note)
        return page

    def _test_page(self):
        page = QWidget();page.setObjectName("balancePage");layout = QVBoxLayout(page)
        box=QGroupBox('Corrección · agregar masa en un plano'); form=QFormLayout(box)
        self.correction_radius=self.spin(.1, 10000, 100, ' mm')
        self.limit=self.spin(0, 1000000, 0, ' g·mm')
        self.limit.setSpecialValueText('Sin límite definido')
        self.blade_one = self.spin(0, 359.99, 0, '°')
        self.blade_count_label = QLabel(str(self.window.blades_spin.value()))
        form.addRow('Radio de corrección:',self.correction_radius)
        form.addRow('N.º álabes (configuración):', self.blade_count_label)
        form.addRow('Ángulo del álabe 1:', self.blade_one)
        form.addRow('Desbalance residual máximo:',self.limit)
        layout.addWidget(box)
        self.test_btn=self.button('1. Medir rotor y calcular corrección',lambda:self.begin_capture('test'))
        layout.addWidget(self.test_btn)
        self.result_label=QLabel('Corrección: —');self.result_label.setWordWrap(True)
        layout.addWidget(self.result_label)
        self.placement_label = QLabel("Colocación por álabes: —")
        self.placement_label.setWordWrap(True)
        layout.addWidget(self.placement_label)
        self.residual_btn=self.button('2. Verificar después de colocar la masa',lambda:self.begin_capture('residual'))
        layout.addWidget(self.residual_btn)
        self.residual_label=QLabel('Residual: —');self.residual_label.setWordWrap(True)
        layout.addWidget(self.residual_label)
        self.new_btn=self.button('Nueva pieza',self.new_piece);layout.addWidget(self.new_btn)
        note=QLabel('Numera los álabes equidistantes desde el 1 en el sentido indicado. Coloca las masas al mismo radio. Usa el perfil, montaje, marca de 0° y sentido angular guardados. La masa de prueba debe estar retirada. Mantén las masas de corrección instaladas durante la verificación.')
        note.setWordWrap(True);layout.addWidget(note)
        layout.addStretch()
        return page

    def _set_message(self, text):
        self.message.setText(text)
        self.test_message.setText(text)

    def settings(self):
        return dict(profile=self.profile.text().strip(),reference=self.reference.text().strip(),
                    direction=self.direction.currentText(), phase_sign=1 if self.phase_sign.currentIndex()==0 else -1,
                    target_rpm=self.rpm.value(),tolerance_pct=self.tolerance.value(),stability_pct=self.stability.value(),
                    **self.live_context())

    def live_context(self):
        w=self.window
        return dict(vref=w.vref,sample_rate=w.SAMPLE_RATE,threshold=w.trigger_threshold.value(),
                    source_kind='simulator' if w.port_combo.currentText()=='SIMULATOR' else 'serial')

    def compatible(self):
        return self.calibration is not None and all(getattr(self.calibration,k)==v for k,v in self.live_context().items())

    def _settings_changed(self,*_):
        if self._loading:return
        self.cancel_capture('Configuración modificada. Repite ambas capturas de calibración.')
        self.initial=self.trial=None
        self.initial_label.setText('Inicial: —');self.trial_label.setText('Con masa de prueba: —');self._buttons()

    def context_changed(self):
        self._settings_changed()
        self.new_piece()
        if self.calibration and not self.compatible():
            self._set_message('La fuente o configuración de señal no coincide con la calibración. Restaura los valores o recalibra.')

    def _buttons(self):
        busy=self.pending is not None
        self.cancel_btn.setEnabled(busy)
        self.test_cancel_btn.setEnabled(busy)
        self.initial_btn.setEnabled(not busy)
        self.trial_btn.setEnabled(not busy and self.initial is not None)
        self.save_btn.setEnabled(not busy and self.initial is not None and self.trial is not None)
        self.test_btn.setEnabled(not busy and self.compatible())
        self.residual_btn.setEnabled(not busy and self.compatible() and self.test is not None)
        for w in self.settings_widgets+[self.load_btn,self.test_load_btn,self.new_btn,self.correction_radius,self.limit,self.blade_one]:w.setEnabled(not busy)

    def begin_capture(self,kind):
        w=self.window
        if self.pending:return
        if not w.source or not w.source.isRunning() or time.monotonic()-w.last_block_time>1:
            self._set_message('Conecta una fuente con datos recientes antes de capturar.');return
        if kind=='trial' and self.initial is None:return
        if kind in ('test','residual') and not self.compatible():
            self._set_message('Calibración ausente o incompatible con la configuración actual.');return
        settings=self.settings() if kind in ('initial','trial') else self.calibration.to_dict()
        if not settings['profile'] or not settings['reference']:
            self._set_message('Completa el perfil de montaje y la referencia de 0°.');return
        if kind=='initial':
            self.initial=self.trial=None;self.initial_label.setText('Inicial: —');self.trial_label.setText('Con masa de prueba: —')
        elif kind=='trial':self.trial=None;self.trial_label.setText('Con masa de prueba: —')
        elif kind=='test':self.new_piece()
        else:self.residual=None;self.residual_label.setText('Residual: —')
        self.pending=dict(kind=kind,readings=[],next_sample=w.total_samples+self.WINDOW_SAMPLES,
                          settings=settings,context=self.live_context(),epoch=w.stream_epoch,started=time.monotonic())
        self._set_message('Capturando 0/3 ventanas nuevas de 2 s…');self._buttons()

    def consume(self,result,end_sample,epoch,context):
        p=self.pending
        if p is None:return
        if epoch!=p['epoch'] or context!=p['context']:return
        if end_sample<p['next_sample']:return
        if not result or not result.get('phase_valid') or result.get('revolutions',0)<3:
            self.cancel_capture('Sin fase válida o sin suficientes revoluciones. Repite la captura.');return
        reading=(result['one_x_amp_counts']*self.window.vref/ADC_MAX,result['phase_deg'],result['rpm'])
        cfg=p['settings']
        if abs(reading[2]-cfg['target_rpm'])/cfg['target_rpm']*100>cfg['tolerance_pct']:
            self.cancel_capture('RPM fuera de tolerancia. Estabiliza la velocidad y repite.');return
        p['readings'].append(reading);p['next_sample']=end_sample+self.WINDOW_SAMPLES
        self._set_message(f"Capturando {len(p['readings'])}/3 ventanas nuevas de 2 s…")
        if len(p['readings'])<self.CAPTURE_WINDOWS:return
        try:
            measured=summarize(p['readings'],cfg['target_rpm'],cfg['tolerance_pct'],cfg['stability_pct'])
            setattr(self,p['kind'],measured)
            if p['kind']=='initial':self.initial_label.setText('Inicial: '+measured.describe())
            elif p['kind']=='trial':self.trial_label.setText('Con masa de prueba: '+measured.describe())
            else:self._show_test()
            self._set_message('Captura estable completada.')
        except ValueError as exc:self._set_message(str(exc))
        self.pending=None;self._buttons()

    def check_freshness(self):
        if self.pending and (time.monotonic()-self.window.last_block_time>1 or time.monotonic()-self.pending['started']>30):
            self.cancel_capture('Captura interrumpida: señal ausente o tiempo de espera agotado.')

    def cancel_capture(self,text):
        was_pending=self.pending is not None
        self.pending=None
        if was_pending:self._set_message(text)
        if hasattr(self,'settings_widgets'):self._buttons()

    def new_piece(self):
        self.cancel_capture('Nueva pieza.');self.test=self.residual=None
        self.result_label.setText('Corrección: —');self.placement_label.setText('Colocación por álabes: —');self.residual_label.setText('Residual: —');self._buttons()

    def _show_test(self,*_):
        self.blade_count_label.setText(str(self.window.blades_spin.value()))
        if self.test is None or not self.compatible():return
        try:
            c=self.calibration;radius=self.correction_radius.value()
            result=correction(self.test,c,radius)
            self.result_label.setText(f"Agregar {result['mass_g']:.3f} g a {result['angle_deg']:.1f}° · {c.direction}\n"
                                      f"Desde: {c.reference} · radio {radius:g} mm\n"
                                      f"Desbalance estimado: {result['unbalance_gmm']:.2f} g·mm · "+self.test.describe())
            self.placement_label.setText(self._placement_text(result, c.direction, radius))
            if self.residual:
                r=correction(self.residual,c,radius);limit=self.limit.value()
                verdict=('CUMPLE' if r['unbalance_gmm']<=limit else 'NO CUMPLE') if limit>0 else 'Sin criterio de aceptación'
                reduction=100*(1-abs(self.residual.vector)/abs(self.test.vector))
                self.residual_label.setText(f"Residual: {r['unbalance_gmm']:.2f} g·mm · {verdict}\n"
                    f"Reducción de amplitud 1X: {reduction:.1f}% · "+self.residual.describe()+
                    f"\nCorrección adicional estimada: {r['mass_g']:.3f} g a {r['angle_deg']:.1f}° · {c.direction}\n"
                    + self._placement_text(r, c.direction, radius))
        except ValueError as exc:self._set_message(str(exc))

    def _placement_text(self, result, direction, radius):
        blades = self.window.blades_spin.value()
        try:
            placements = distribute_on_blades(result['mass_g'], result['angle_deg'], blades, self.blade_one.value())
        except ValueError as exc:
            return 'Colocación por álabes: ' + str(exc)
        lines = [f'Colocación · {blades} álabes · numeración en sentido {direction.lower()}:']
        for number, mass, angle in placements:
            lines.append(f'Álabe {number}: agregar {mass:.3f} g a {angle:.1f}°')
        lines.append(f'Mismo plano y radio {radius:g} mm. Álabe 1 a {self.blade_one.value():g}° desde la marca de 0°.')
        return '\n'.join(lines)

    def save_calibration(self):
        if not self.initial or not self.trial:return
        try:
            c=calibrate(self.initial,self.trial,mass=self.mass.value(),radius=self.radius.value(),angle=self.angle.value(),**self.settings())
            path,_=QFileDialog.getSaveFileName(self,'Guardar calibración',str(Path.home()/'calibracion_1_plano.json'),'Calibración (*.json)')
            if not path:return
            if not path.lower().endswith('.json'):path+='.json'
            Path(path).write_text(json.dumps(c.to_dict(),ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
            self.activate(c,path)
            self._set_message('Calibración guardada. Retira la masa de prueba antes de medir una pieza.')
        except (ValueError,OSError) as exc:self._set_message(str(exc))

    def load_calibration(self):
        path,_=QFileDialog.getOpenFileName(self,'Cargar calibración','','Calibración (*.json)')
        if not path:return
        try:
            c=Calibration.from_dict(json.loads(Path(path).read_text(encoding='utf-8')))
            self.activate(c,path)
            self._set_message('Calibración cargada. Confirma el montaje y la referencia física antes de medir.' if self.compatible() else
                                 'Archivo cargado, pero la fuente/ADC/trigger no coincide. Restaura la configuración o recalibra.')
        except (ValueError,TypeError,OSError) as exc:self._set_message(f'No se pudo cargar: {exc}')

    def activate(self,c,path):
        self.calibration=c;self.saved_path=path;self._loading=True
        self.profile.setText(c.profile);self.reference.setText(c.reference)
        self.direction.setCurrentText(c.direction);self.phase_sign.setCurrentIndex(0 if c.phase_sign==1 else 1)
        self.rpm.setValue(c.target_rpm);self.tolerance.setValue(c.tolerance_pct);self.stability.setValue(c.stability_pct)
        self.mass.setValue(c.trial_mass_g);self.radius.setValue(c.trial_radius_mm);self.angle.setValue(c.trial_angle_deg)
        self.correction_radius.setValue(c.trial_radius_mm)
        self._loading=False;self.initial=self.trial=None
        self.initial_label.setText('Inicial: —');self.trial_label.setText('Con masa de prueba: —')
        label='SIMULADOR · ' if c.source_kind=='simulator' else ''
        self.summary.setText(f'{label}{c.profile} · {c.target_rpm:g} RPM · 0°: {c.reference} · {c.direction}\n'
                             f'α = {c.alpha_real:.6g} {c.alpha_imag:+.6g}j V/(g·mm) · {Path(path).name}')
        self.test_summary.setText(self.summary.text())
        self.new_piece();self._buttons()
        self.window.plot_tabs.setCurrentIndex(1)
