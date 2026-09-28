import numpy as np
from protocol import (
    encode_packet, PacketParser, BlockAssembler,
    HEADER_VIBRATION, HEADER_TRIGGER, SAMPLES_PER_PACKET,
)
from analysis_core import analyze_block


def test_protocol():
    ch1 = np.arange(SAMPLES_PER_PACKET, dtype=np.uint16)
    ch2 = (1000 + np.arange(SAMPLES_PER_PACKET, dtype=np.uint16))
    stream = encode_packet(HEADER_VIBRATION, 42, ch1) + encode_packet(HEADER_TRIGGER, 42, ch2)

    parser = PacketParser()
    assembler = BlockAssembler()
    blocks = []
    for pos in range(0, len(stream), 73):
        for packet in parser.feed(stream[pos:pos+73]):
            block = assembler.add(packet)
            if block:
                blocks.append(block)

    assert len(blocks) == 1
    assert blocks[0].sequence == 42
    assert np.array_equal(blocks[0].vibration, ch1)
    assert np.array_equal(blocks[0].trigger, ch2)


def test_analysis():
    fs = 2000.0
    rpm = 1800.0
    f = rpm / 60.0
    n = 4000
    t = np.arange(n) / fs
    phase_deg = 125.0
    vibration = 2048 + 600*np.cos(2*np.pi*f*t - np.deg2rad(phase_deg))
    trigger = 2048 + 1400*np.sin(2*np.pi*f*t)
    vibration = np.clip(np.rint(vibration), 0, 4095).astype(np.uint16)
    trigger = np.clip(np.rint(trigger), 0, 4095).astype(np.uint16)

    result = analyze_block(vibration, trigger, fs, 2048, 7)
    assert abs(result['rpm'] - rpm) < 5.0
    assert abs(result['bpf_hz'] - 210.0) < 1.0
    assert result['one_x_amp_counts'] > 500


if __name__ == '__main__':
    test_protocol()
    test_analysis()
    print('OK: protocol + analysis')
