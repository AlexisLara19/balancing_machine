"""GUI workflow and persistence smoke test. Run with QT_QPA_PLATFORM=offscreen."""
import math
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

from PyQt6.QtWidgets import QApplication, QFileDialog
from PyQt6.QtTest import QTest
from app import MainWindow
from calibration_core import phasor
from protocol import ADC_MAX


class TestSource:
    def isRunning(self): return True
    def stop(self): pass
    def wait(self, *_): pass


def main():
    app = QApplication([])
    app.setStyle('Fusion')
    w = MainWindow()
    try:
        w.show()
        w.plot_tabs.setCurrentIndex(2)
        p = w.balancing
        p.mode.setCurrentIndex(1)
        p.profile.setText('DEMOSTRACIÓN / Rotor A')
        p.reference.setText('Marca del cubo')
        w.start_source()
        QTest.qWait(250)
        p.begin_capture('initial')
        QTest.qWait(7000)
        assert p.initial is not None, p.message.text()
        assert not w.render_timer.isActive()
        w.stop_source()
        QTest.qWait(100)
        w.source = TestSource()

        def capture(kind, vector):
            w.last_block_time = time.monotonic()
            p.begin_capture(kind)
            assert p.pending is not None, p.message.text()
            result = dict(phase_valid=True, revolutions=59,
                          one_x_amp_counts=abs(vector)*ADC_MAX/w.vref,
                          phase_deg=math.degrees(math.atan2(vector.imag, vector.real)) % 360,
                          rpm=1800)
            for _ in range(3):
                end = p.pending['next_sample']
                # A duplicated/old window must not count as another observation.
                p.consume(result, end-1, w.stream_epoch, p.live_context())
                w.total_samples = end
                p.consume(result, end, w.stream_epoch, p.live_context())
            assert p.pending is None, p.message.text()

        alpha = phasor(.002, 35)
        base = alpha*phasor(250, 80)
        capture('initial', base)
        capture('trial', base+alpha*phasor(100, 0))
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory)/'cal.json')
            with patch.object(QFileDialog, 'getSaveFileName', return_value=(path, '')):
                p.save_calibration()
            assert p.calibration is not None and Path(path).is_file(), p.message.text()
            with patch.object(QFileDialog, 'getOpenFileName', return_value=(path, '')):
                p.load_calibration()
            assert p.compatible()
            capture('test', base)
            assert '2.500 g' in p.result_label.text() and '260.0°' in p.result_label.text()
            p.limit.setValue(20)
            capture('residual', alpha*phasor(10, 80))
            assert 'CUMPLE' in p.residual_label.text()
            p.limit.setValue(5)
            assert 'NO CUMPLE' in p.residual_label.text()
            p.new_piece()
            assert p.test is None and p.residual is None
            p.begin_capture('test')
            p.consume({}, p.pending['next_sample'], w.stream_epoch, p.live_context())
            assert p.pending is None
            p.begin_capture('test')
            w.last_block_time = time.monotonic()-2
            p.check_freshness()
            assert p.pending is None
            w.vref_spin.setValue(3.2)
            assert not p.compatible() and not p.test_btn.isEnabled()
        w.plot_tabs.setCurrentIndex(0)
        assert w.render_timer.isActive()
        print('OK: live capture, non-overlapping windows, save/load, correction, residual and rejection gates')
    finally:
        w.close()


if __name__ == '__main__':
    main()
