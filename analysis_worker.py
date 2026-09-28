from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot
from analysis_core import analyze_block


class AnalysisWorker(QObject):
    result_ready = pyqtSignal(dict)
    error = pyqtSignal(str)

    @pyqtSlot(object, object, float, float, int)
    def analyze(self, vibration, trigger, sample_rate, threshold, blades):
        try:
            result = analyze_block(vibration, trigger, sample_rate, threshold, blades)
            self.result_ready.emit(result)
        except Exception as exc:
            self.error.emit(str(exc))
            self.result_ready.emit({})
