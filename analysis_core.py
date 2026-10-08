from __future__ import annotations

import numpy as np


def detect_rising_crossings(signal: np.ndarray, threshold: float) -> np.ndarray:
    """Índices fraccionales de cruces ascendentes usando interpolación lineal."""
    y = np.asarray(signal, dtype=np.float64)
    if y.size < 2:
        return np.empty(0, dtype=np.float64)

     # Los indices del arreglo cuando se produce un flanco ascendente
    idx = np.flatnonzero((y[:-1] < threshold) & (y[1:] >= threshold))
    if idx.size == 0:
        return np.empty(0, dtype=np.float64)

    y0 = y[idx]
    y1 = y[idx + 1]
    denom = y1 - y0
    frac = np.zeros_like(y0, dtype=np.float64)
    valid = denom != 0
    # Interpolamos para aproximar el valor de tiempo del cruce por cero entre dos muestras
    frac[valid] = (threshold - y0[valid]) / denom[valid]
    # valor de tiempo en segundos: La parte entera  + la parte fraccionaria 
    return idx.astype(np.float64) + np.clip(frac, 0.0, 1.0)


def dominant_frequency(signal: np.ndarray, sample_rate: float) -> float:
    y = np.asarray(signal, dtype=np.float64)
    if y.size < 8 or sample_rate <= 0:
        return 0.0

    # Eliminamos la componente DC, centramos la senial en 0
    y = y - np.mean(y)

    # Ventana de Hanning para suavizar discontinuidades  antes de calcular Fourier
    spectrum = np.abs(np.fft.rfft(y * np.hanning(y.size)))

    # Frecuencias a las que se realiza el muestreo
    freqs = np.fft.rfftfreq(y.size, 1.0 / sample_rate)
    if spectrum.size <= 1:
        return 0.0
    spectrum[0] = 0.0

    # Retorna la frecuencia con el valor mas alto
    return float(freqs[int(np.argmax(spectrum))])


def analyze_block(vibration: np.ndarray, trigger: np.ndarray, sample_rate: float,
                  threshold: float, blades: int) -> dict:
    v = np.asarray(vibration, dtype=np.float64)
    t = np.asarray(trigger, dtype=np.float64)
    n = min(v.size, t.size)
    if n < 8 or sample_rate <= 0:
        return {}

    # Arreglos de la misma longitud de datos
    v, t = v[:n], t[:n]

    # Eliminar componente DC. Centrar en 0
    v_ac = v - np.mean(v) 

    # Valores para la ventana de mediciones de oscilocopio
    rms_counts = float(np.sqrt(np.mean(v_ac * v_ac)))
    peak_counts = float(np.max(np.abs(v_ac)))
    p2p_counts = float(np.ptp(v))
    crest_factor = peak_counts / rms_counts if rms_counts > 0 else 0.0
    dom_freq = dominant_frequency(v, sample_rate)

    # Deteccion de cruce por cero en el trigger
    crossings = detect_rising_crossings(t, threshold)
    rpm = 0.0
    rot_hz = 0.0
    one_x_amp = 0.0
    phase_deg = 0.0
    phase_valid = False
    revolutions = max(0, crossings.size - 1)

    if crossings.size >= 2:

        # Obtenemos los cruces por cero que sean significativos
        periods_samples = np.diff(crossings) # [xi+1 - xi , ..... , xn - xn-1]
        valid_periods = periods_samples[periods_samples > 0] # [ D1, D2, D3, ... ,Dn]
        if valid_periods.size:
            mean_period = float(np.mean(valid_periods))
            rot_hz = sample_rate / mean_period
            rpm = rot_hz * 60.0

        # Order tracking simple: cada intervalo trigger-trigger representa 0..360°.
        cos_acc = 0.0
        sin_acc = 0.0
        used = 0

        # Cada par representa una revolucion completa
        # C0 y C1 son las posiciones en el arreglo entre los que se encuentran los datos
        for c0, c1 in zip(crossings[:-1], crossings[1:]): 
            i0 = max(0, int(np.ceil(c0))) # Inicio de revolucion
            i1 = min(n, int(np.floor(c1)) + 1) # Final de revolucion
            if i1 - i0 < 4:
                continue

            # Construimos el eje de las abscisas X(t)
            idx = np.arange(i0, i1, dtype=np.float64)

            ## Calculo del Fasor X_1

            # Fase del trigger
            theta = 2.0 * np.pi * (idx - c0) / (c1 - c0)

            # Sgmento de la senial V(t) al que corresponde X(t)
            segment = v_ac[i0:i1]

            # Proyeccion a componentes polares
            cos_acc += float(np.sum(segment * np.cos(theta)))
            sin_acc += float(np.sum(segment * np.sin(theta)))
            used += segment.size

        if used:
            # Normalizacion de resultados (promedio dinamico)
            a = 2.0 * cos_acc / used
            b = 2.0 * sin_acc / used

            # Calculo de magnitud de desbalanceo
            one_x_amp = float(np.hypot(a, b))

            # Calculo de la fase de desbalanceo
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
