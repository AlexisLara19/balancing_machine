"""Single-plane influence calibration. All angles are degrees, masses g, radii mm."""
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
import cmath
import math


def positive(value, name):
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f'{name} debe ser finito y mayor que cero.')


def phasor(amplitude, phase):
    return cmath.rect(amplitude, math.radians(phase))


@dataclass(frozen=True)
class Measurement:
    vector: complex
    rpm: float
    scatter: float
    count: int

    def describe(self):
        return f'{abs(self.vector):.4f} V · {math.degrees(cmath.phase(self.vector)) % 360:.1f}° · {self.rpm:.1f} RPM'


def summarize(readings, target_rpm, tolerance_pct, stability_pct):
    if len(readings) < 3:
        raise ValueError('Se requieren tres ventanas independientes de señal.')
    vectors, speeds = [], []
    for amplitude, phase, rpm in readings:
        positive(amplitude, 'Amplitud')
        positive(rpm, 'RPM')
        if not math.isfinite(phase):
            raise ValueError('Fase inválida.')
        if abs(rpm - target_rpm) / target_rpm * 100 > tolerance_pct:
            raise ValueError('RPM fuera de la tolerancia configurada.')
        vectors.append(phasor(amplitude, phase))
        speeds.append(rpm)
    mean = sum(vectors) / len(vectors)
    scatter = math.sqrt(sum(abs(v - mean)**2 for v in vectors) / len(vectors))
    if abs(mean) <= 1e-9 or scatter / abs(mean) * 100 > stability_pct:
        raise ValueError('Amplitud/fase inestables; repite la captura.')
    if (max(speeds) - min(speeds)) / target_rpm * 100 > tolerance_pct:
        raise ValueError('La velocidad varió durante la captura.')
    return Measurement(mean, sum(speeds) / len(speeds), scatter, len(vectors))


@dataclass(frozen=True)
class Calibration:
    profile: str
    reference: str
    direction: str
    phase_sign: int
    target_rpm: float
    tolerance_pct: float
    stability_pct: float
    vref: float
    sample_rate: float
    threshold: int
    source_kind: str
    alpha_real: float
    alpha_imag: float
    trial_mass_g: float
    trial_radius_mm: float
    trial_angle_deg: float
    created_at: str
    schema_version: int = 1

    @property
    def alpha(self):
        return complex(self.alpha_real, self.alpha_imag)

    def validate(self):
        if self.schema_version != 1 or self.phase_sign not in (-1, 1):
            raise ValueError('Formato de calibración no compatible.')
        if self.direction not in ('Horario', 'Antihorario') or self.source_kind not in ('simulator', 'serial'):
            raise ValueError('Convención angular o fuente inválida.')
        if not isinstance(self.profile, str) or not self.profile.strip() or not isinstance(self.reference, str) or not self.reference.strip():
            raise ValueError('Define el perfil de montaje y la marca de 0°.')
        for name in ('target_rpm', 'tolerance_pct', 'stability_pct', 'vref', 'sample_rate', 'trial_mass_g', 'trial_radius_mm'):
            positive(getattr(self, name), name)
        if not (0 < self.tolerance_pct <= 10 and 0 < self.stability_pct <= 50):
            raise ValueError('Tolerancias fuera del rango permitido.')
        if not isinstance(self.threshold, int) or not 0 <= self.threshold <= 4095:
            raise ValueError('Umbral ADC inválido.')
        if not math.isfinite(self.trial_angle_deg) or not 0 <= self.trial_angle_deg < 360:
            raise ValueError('Ángulo de prueba inválido.')
        if not math.isfinite(self.alpha_real) or not math.isfinite(self.alpha_imag) or abs(self.alpha) <= 1e-12:
            raise ValueError('Coeficiente de influencia inválido.')
        return self

    def to_dict(self):
        self.validate()
        return asdict(self)

    @classmethod
    def from_dict(cls, data):
        try:
            return cls(**data).validate()
        except (TypeError, KeyError, OverflowError) as exc:
            raise ValueError('Archivo de calibración incompleto o inválido.') from exc


def calibrate(initial, trial, *, mass, radius, angle, **settings):
    positive(mass, 'Masa de prueba')
    positive(radius, 'Radio de prueba')
    delta = trial.vector - initial.vector
    uncertainty = math.hypot(initial.scatter, trial.scatter)
    minimum = max(5 * uncertainty, .05 * max(abs(initial.vector), abs(trial.vector)), 1e-6)
    if abs(delta) <= minimum:
        raise ValueError('La masa de prueba no produjo un cambio suficiente frente a la variación. No se puede calibrar.')
    if abs(initial.rpm - trial.rpm) / settings['target_rpm'] * 100 > settings['tolerance_pct']:
        raise ValueError('Las dos capturas tienen velocidades incompatibles.')
    u_trial = phasor(mass * radius, settings['phase_sign'] * angle)
    alpha = delta / u_trial
    return Calibration(**settings, alpha_real=alpha.real, alpha_imag=alpha.imag,
                       trial_mass_g=mass, trial_radius_mm=radius, trial_angle_deg=angle,
                       created_at=datetime.now(timezone.utc).isoformat()).validate()


def correction(measurement, calibration, radius):
    calibration.validate()
    positive(radius, 'Radio de corrección')
    positive(measurement.rpm, 'RPM')
    if abs(measurement.rpm - calibration.target_rpm) / calibration.target_rpm * 100 > calibration.tolerance_pct:
        raise ValueError('La velocidad no corresponde a la calibración.')
    u = -measurement.vector / calibration.alpha
    return {'mass_g': abs(u) / radius, 'unbalance_gmm': abs(u),
            'angle_deg': (calibration.phase_sign * math.degrees(cmath.phase(u))) % 360}
