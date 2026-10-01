from __future__ import annotations

import numpy as np


def detect_rising_crossings(signal: np.ndarray, threshold: float) -> np.ndarray:
    """Índices fraccionales de cruces ascendentes usando interpolación lineal."""
    y = np.asarray(signal, dtype=np.float64)
    if y.size < 2:
        return np.empty(0, dtype=np.float64)

    idx = np.flatnonzero((y[:-1] < threshold) & (y[1:] >= threshold))
    if idx.size == 0:
        return np.empty(0, dtype=np.float64)

    y0 = y[idx]
    y1 = y[idx + 1]
    denom = y1 - y0
    frac = np.zeros_like(y0, dtype=np.float64)
    valid = denom != 0
    frac[valid] = (threshold - y0[valid]) / denom[valid]
    return idx.astype(np.float64) + np.clip(frac, 0.0, 1.0)


def dominant_frequency(signal: np.ndarray, sample_rate: float) -> float:
    y = np.asarray(signal, dtype=np.float64)
    if y.size < 8 or sample_rate <= 0:
        return 0.0
    y = y - np.mean(y)
    spectrum = np.abs(np.fft.rfft(y * np.hanning(y.size)))
    freqs = np.fft.rfftfreq(y.size, 1.0 / sample_rate)
    if spectrum.size <= 1:
        return 0.0
    spectrum[0] = 0.0
    return float(freqs[int(np.argmax(spectrum))])


def analyze_block(vibration: np.ndarray, trigger: np.ndarray, sample_rate: float,
                  threshold: float, blades: int) -> dict:
    v = np.asarray(vibration, dtype=np.float64)
    t = np.asarray(trigger, dtype=np.float64)
    n = min(v.size, t.size)
    if n < 8 or sample_rate <= 0:
        return {}
    v, t = v[:n], t[:n]

    v_ac = v - np.mean(v)
    rms_counts = float(np.sqrt(np.mean(v_ac * v_ac)))
    peak_counts = float(np.max(np.abs(v_ac)))
    p2p_counts = float(np.ptp(v))
    crest_factor = peak_counts / rms_counts if rms_counts > 0 else 0.0
    dom_freq = dominant_frequency(v, sample_rate)

    crossings = detect_rising_crossings(t, threshold)
    rpm = 0.0
    rot_hz = 0.0
    one_x_amp = 0.0
    phase_deg = 0.0
    phase_valid = False
    revolutions = max(0, crossings.size - 1)

    if crossings.size >= 2:
        periods_samples = np.diff(crossings)
        valid_periods = periods_samples[periods_samples > 0]
        if valid_periods.size:
            mean_period = float(np.mean(valid_periods))
            rot_hz = sample_rate / mean_period
            rpm = rot_hz * 60.0

        # Order tracking simple: cada intervalo trigger-trigger representa 0..360°.
        cos_acc = 0.0
        sin_acc = 0.0
        used = 0
        for c0, c1 in zip(crossings[:-1], crossings[1:]):
            i0 = max(0, int(np.ceil(c0)))
            i1 = min(n, int(np.floor(c1)) + 1)
            if i1 - i0 < 4:
                continue
            idx = np.arange(i0, i1, dtype=np.float64)
            theta = 2.0 * np.pi * (idx - c0) / (c1 - c0)
            segment = v_ac[i0:i1]
            cos_acc += float(np.sum(segment * np.cos(theta)))
            sin_acc += float(np.sum(segment * np.sin(theta)))
            used += segment.size

        if used:
            a = 2.0 * cos_acc / used
            b = 2.0 * sin_acc / used
            one_x_amp = float(np.hypot(a, b))
            # Convención: y ≈ A*cos(theta - phase). Trigger ascendente = 0°.
            phase_deg = float(np.degrees(np.arctan2(b, a)) % 360.0)
            phase_valid = bool(one_x_amp > 0 and np.isfinite(one_x_amp) and np.isfinite(phase_deg))

    return {
        'rms_counts': rms_counts,
        'peak_counts': peak_counts,
        'p2p_counts': p2p_counts,
        'crest_factor': crest_factor,
        'dominant_hz': dom_freq,
        'rpm': rpm,
        'rot_hz': rot_hz,
        'one_x_amp_counts': one_x_amp,
        'phase_deg': phase_deg,
        'phase_valid': phase_valid,
        'bpf_hz': rot_hz * max(1, int(blades)),
        'revolutions': int(revolutions),
        'trigger_crossings': int(crossings.size),
    }
