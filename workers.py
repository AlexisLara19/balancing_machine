from __future__ import annotations

import time
import threading
import numpy as np
import serial
from PyQt6.QtCore import QThread, QObject, pyqtSignal, pyqtSlot

from protocol import (
    PacketParser, BlockAssembler, SampleBlock,
    HEADER_VIBRATION, HEADER_TRIGGER, SAMPLES_PER_PACKET, ADC_MAX,
    encode_packet,
)


class SerialReader(QThread):
    bytes_received = pyqtSignal(bytes)
    connected = pyqtSignal()
    disconnected = pyqtSignal()
    error = pyqtSignal(str)
    throughput = pyqtSignal(int)

    def __init__(self, port: str, baudrate: int, parent=None):
        super().__init__(parent)
        self.port = port
        self.baudrate = int(baudrate)
        self._stop_event = threading.Event()

    def stop(self):
        self._stop_event.set()

    def run(self):
        ser = None
        try:
            ser = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=0.02,
            )
            self.connected.emit()
            byte_count = 0
            last = time.monotonic()

            while not self._stop_event.is_set():
                waiting = ser.in_waiting
                data = ser.read(waiting or 1)
                if data:
                    byte_count += len(data)
                    self.bytes_received.emit(data)

                now = time.monotonic()
                if now - last >= 1.0:
                    self.throughput.emit(byte_count)
                    byte_count = 0
                    last = now
        except Exception as exc:
            self.error.emit(str(exc))
        finally:
            if ser is not None:
                try:
                    ser.close()
                except Exception:
                    pass
            self.disconnected.emit()


class SimulatorReader(QThread):
    """Genera el mismo stream de bytes que la PSoC, a 2000 SPS por canal."""

    bytes_received = pyqtSignal(bytes)
    connected = pyqtSignal()
    disconnected = pyqtSignal()
    throughput = pyqtSignal(int)

    def __init__(self, sample_rate=2000.0, rpm=1800.0, parent=None):
        super().__init__(parent)
        self.sample_rate = float(sample_rate)
        self.rpm = float(rpm)
        self._stop_event = threading.Event()
        self._rng = np.random.default_rng()

    def stop(self):
        self._stop_event.set()

    def run(self):
        self.connected.emit()
        sequence = 0
        sample_index = 0
        bytes_last_second = 0
        stat_t0 = time.monotonic()
        block_period = SAMPLES_PER_PACKET / self.sample_rate
        next_deadline = time.monotonic()

        try:
            while not self._stop_event.is_set():
                rpm = max(1.0, float(self.rpm))
                f_rot = rpm / 60.0
                idx = sample_index + np.arange(SAMPLES_PER_PACKET, dtype=np.float64)
                time_s = idx / self.sample_rate

                # CH1: vibración 1X + armónico débil + ruido, centrada en mitad de escala.
                phase = np.deg2rad(125.0)
                vibration = (
                    2048.0
                    + 650.0 * np.cos(2*np.pi*f_rot*time_s - phase)
                    + 110.0 * np.cos(2*np.pi*2*f_rot*time_s + 0.4)
                    + self._rng.normal(0.0, 28.0, SAMPLES_PER_PACKET)
                )

                # CH2: señal analógica periódica. El cruce ascendente por 2048 define 0°.
                trigger = 2048.0 + 1450.0 * np.sin(2*np.pi*f_rot*time_s)

                vibration = np.clip(np.rint(vibration), 0, ADC_MAX).astype(np.uint16)
                trigger = np.clip(np.rint(trigger), 0, ADC_MAX).astype(np.uint16)

                stream = (
                    encode_packet(HEADER_VIBRATION, sequence, vibration)
                    + encode_packet(HEADER_TRIGGER, sequence, trigger)
                )

                # Fragmentación deliberada para probar que el parser no depende de read() completos.
                pos = 0
                while pos < len(stream):
                    chunk_len = int(self._rng.integers(37, 121))
                    chunk = stream[pos:pos + chunk_len]
                    self.bytes_received.emit(chunk)
                    bytes_last_second += len(chunk)
                    pos += len(chunk)

                sequence = (sequence + 1) & 0xFFFF
                sample_index += SAMPLES_PER_PACKET

                now = time.monotonic()
                if now - stat_t0 >= 1.0:
                    self.throughput.emit(bytes_last_second)
                    bytes_last_second = 0
                    stat_t0 = now

                next_deadline += block_period
                delay = next_deadline - time.monotonic()
                if delay > 0:
                    self._stop_event.wait(delay)
                else:
                    next_deadline = time.monotonic()
        finally:
            self.disconnected.emit()


class ProtocolWorker(QObject):
    block_ready = pyqtSignal(object)
    diagnostics = pyqtSignal(dict)

    def __init__(self):
        super().__init__()
        self.parser = PacketParser()
        self.assembler = BlockAssembler()

    @pyqtSlot()
    def reset(self):
        self.parser.reset()
        self.assembler.reset()
        self._emit_diagnostics()

    @pyqtSlot(bytes)
    def feed(self, data: bytes):
        for packet in self.parser.feed(data):
            block = self.assembler.add(packet)
            if block is not None:
                self.block_ready.emit(block)
        self._emit_diagnostics()

    def _emit_diagnostics(self):
        self.diagnostics.emit({
            'good_packets': self.parser.good_packets,
            'bad_crc': self.parser.bad_crc,
            'bad_adc': self.parser.bad_adc,
            'discarded_bytes': self.parser.discarded_bytes,
            'blocks': self.assembler.completed_blocks,
            'dropped_sequences': self.assembler.dropped_sequences,
        })
