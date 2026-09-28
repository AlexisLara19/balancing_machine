from __future__ import annotations

from dataclasses import dataclass
import struct
import numpy as np

HEADER_VIBRATION = 0xAA
HEADER_TRIGGER = 0x55
VALID_HEADERS = (HEADER_VIBRATION, HEADER_TRIGGER)
SAMPLES_PER_PACKET = 256
BYTES_PER_SAMPLE = 2
PAYLOAD_SIZE = SAMPLES_PER_PACKET * BYTES_PER_SAMPLE
PACKET_SIZE = 1 + 2 + PAYLOAD_SIZE + 2  # header + sequence + payload + CRC16
ADC_BITS = 12
ADC_MAX = (1 << ADC_BITS) - 1


def crc16_ccitt(data: bytes, crc: int = 0xFFFF) -> int:
    """CRC-16/CCITT-FALSE: poly=0x1021, init=0xFFFF."""
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc


@dataclass(slots=True)
class ChannelPacket:
    channel: int
    sequence: int
    samples: np.ndarray


@dataclass(slots=True)
class SampleBlock:
    sequence: int
    vibration: np.ndarray
    trigger: np.ndarray


def encode_packet(header: int, sequence: int, samples: np.ndarray) -> bytes:
    """Encoder usado por el simulador y útil como referencia para el firmware PSoC."""
    if header not in VALID_HEADERS:
        raise ValueError('Header no válido')

    samples = np.asarray(samples, dtype=np.uint16)
    if samples.size != SAMPLES_PER_PACKET:
        raise ValueError(f'Se requieren exactamente {SAMPLES_PER_PACKET} muestras')
    if np.any(samples > ADC_MAX):
        raise ValueError(f'Las muestras de 12 bits deben estar entre 0 y {ADC_MAX}')

    body = bytes([header]) + struct.pack('<H', sequence & 0xFFFF) + samples.astype('<u2', copy=False).tobytes()
    crc = crc16_ccitt(body)
    return body + struct.pack('<H', crc)


class PacketParser:
    """UART con paquetes de longitud fija."""

    def __init__(self):
        self.buffer = bytearray()
        self.good_packets = 0
        self.bad_crc = 0
        self.bad_adc = 0
        self.discarded_bytes = 0

    def reset(self) -> None:
        self.buffer.clear()
        self.good_packets = 0
        self.bad_crc = 0
        self.bad_adc = 0
        self.discarded_bytes = 0

    def feed(self, data: bytes) -> list[ChannelPacket]:
        if not data:
            return []
        self.buffer.extend(data)
        out: list[ChannelPacket] = []

        while True:
            if len(self.buffer) < PACKET_SIZE:
                break

            # Buscar el primer byte que pueda ser cabecera en buffer
            start = next((i for i, b in enumerate(self.buffer) if b in VALID_HEADERS), -1)

            if start < 0:
                self.discarded_bytes += len(self.buffer)
                self.buffer.clear()
                break
            if start:
                self.discarded_bytes += start
                del self.buffer[:start]
                if len(self.buffer) < PACKET_SIZE:
                    break

            candidate = bytes(self.buffer[:PACKET_SIZE])
            received_crc = struct.unpack_from('<H', candidate, PACKET_SIZE - 2)[0]
            calculated_crc = crc16_ccitt(candidate[:-2])

            if received_crc != calculated_crc:
                self.bad_crc += 1
                self.discarded_bytes += 1
                del self.buffer[0]
                continue

            header = candidate[0]
            sequence = struct.unpack_from('<H', candidate, 1)[0]
            samples = np.frombuffer(candidate, dtype='<u2', count=SAMPLES_PER_PACKET, offset=3).copy()

            # ADC 12 BITS
            if np.any(samples > ADC_MAX):
                self.bad_adc += 1
                del self.buffer[:PACKET_SIZE]
                continue

            out.append(ChannelPacket(header, sequence, samples))
            self.good_packets += 1
            del self.buffer[:PACKET_SIZE]

        return out


class BlockAssembler:
    """Empareja CH1(0xAA) y CH2(0x55) mediante el mismo sequence number."""

    def __init__(self, max_pending: int = 8):
        self.pending: dict[int, dict[int, np.ndarray]] = {}
        self.max_pending = max_pending
        self.completed_blocks = 0
        self.dropped_sequences = 0

    def reset(self) -> None:
        self.pending.clear()
        self.completed_blocks = 0
        self.dropped_sequences = 0

    def add(self, packet: ChannelPacket) -> SampleBlock | None:
        slot = self.pending.setdefault(packet.sequence, {})
        slot[packet.channel] = packet.samples

        if HEADER_VIBRATION in slot and HEADER_TRIGGER in slot:
            block = SampleBlock(
                sequence=packet.sequence,
                vibration=slot[HEADER_VIBRATION],
                trigger=slot[HEADER_TRIGGER],
            )
            del self.pending[packet.sequence]
            self.completed_blocks += 1
            self._trim_pending()
            return block

        self._trim_pending()
        return None

    def _trim_pending(self) -> None:
        while len(self.pending) > self.max_pending:
            # dict preserva orden de inserción; descartamos el bloque incompleto más antiguo.
            oldest = next(iter(self.pending))
            del self.pending[oldest]
            self.dropped_sequences += 1
