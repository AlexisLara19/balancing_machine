"""Calibración de influencia en un solo plano. Todos los ángulos están en grados, las masas en g y los radios en mm."""
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
import cmath
import math


# -----------
# Utilidades
# -----------

def positive(value, name):
    # Asegura que un parámetro sea numérico, finito y estrictamente positivo.
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f'{name} debe ser finito y mayor que cero.')


def phasor(amplitude, phase):
    # Convierte una amplitud y un ángulo en un fasor complejo representando un vector rotatorio.
    return cmath.rect(amplitude, math.radians(phase))


# -------------------
# Medición resumida
# -------------------

@dataclass(frozen=True)
class Measurement:
    vector: complex
    rpm: float
    scatter: float
    count: int

    def describe(self):
        # Devuelve un texto legible para depuración y visualización del vector medio capturado.
        return f'{abs(self.vector):.4f} V · {math.degrees(cmath.phase(self.vector)) % 360:.1f}° · {self.rpm:.1f} RPM'


def summarize(readings, target_rpm, tolerance_pct, stability_pct):
    # Agrupa varias ventanas de señal y calcula el vector medio junto con su dispersión.
    # Este resultado se usa como referencia para detectar si la captura es estable y útil para calibrar.
    if len(readings) < 3:
        raise ValueError('Se requieren tres ventanas independientes de señal.')
    vectors, speeds = [], []
    for amplitude, phase, rpm in readings:
        # Cada lectura debe tener amplitud válida, fase finita y velocidad dentro de la tolerancia.
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
    # Si el vector medio casi desaparece o la dispersión es demasiado grande, la señal no es confiable.
    if abs(mean) <= 1e-9 or scatter / abs(mean) * 100 > stability_pct:
        raise ValueError('Amplitud/fase inestables; repite la captura.')
    # La velocidad también debe mantenerse estable durante la ventana de captura.
    if (max(speeds) - min(speeds)) / target_rpm * 100 > tolerance_pct:
        raise ValueError('La velocidad varió durante la captura.')
    return Measurement(mean, sum(speeds) / len(speeds), scatter, len(vectors))


# ----------------
# Perfil de calibración
# ----------------

@dataclass(frozen=True)
class Calibration:
    # Almacena un perfil completo que describe la geometría, la fuente de datos y el coeficiente de influencia.
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
        # Coeficiente complejo que relaciona un desbalance con el vector observado al rotor.
        return complex(self.alpha_real, self.alpha_imag)

    def validate(self):
        # Verifica la compatibilidad del schema, la orientación angular y la integridad de los parámetros físicos.
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
        # Serializa la calibración para guardarla en JSON o en un archivo de configuración.
        self.validate()
        return asdict(self)

    @classmethod
    def from_dict(cls, data):
        # Reconstruye el objeto a partir de un diccionario leído desde archivo.
        try:
            return cls(**data).validate()
        except (TypeError, KeyError, OverflowError) as exc:
            raise ValueError('Archivo de calibración incompleto o inválido.') from exc


# ------------------------------
# Cálculo del coeficiente α
# ------------------------------

def calibrate(initial, trial, *, mass, radius, angle, **settings):
    # Calcula el vector de influencia usando dos mediciones: una base y otra con una masa conocida en un ángulo conocido.
    positive(mass, 'Masa de prueba')
    positive(radius, 'Radio de prueba')
    delta = trial.vector - initial.vector
    uncertainty = math.hypot(initial.scatter, trial.scatter)
    # El cambio mínimo debe superar la variación natural de la medición para que la calibración sea significativa.
    minimum = max(5 * uncertainty, .05 * max(abs(initial.vector), abs(trial.vector)), 1e-6)
    if abs(delta) <= minimum:
        raise ValueError('La masa de prueba no produjo un cambio suficiente frente a la variación. No se puede calibrar.')
    if abs(initial.rpm - trial.rpm) / settings['target_rpm'] * 100 > settings['tolerance_pct']:
        raise ValueError('Las dos capturas tienen velocidades incompatibles.')
    # El vector generado por la masa de prueba se expresa en unidades de g·mm con su fase angular.
    u_trial = phasor(mass * radius, settings['phase_sign'] * angle)
    alpha = delta / u_trial
    return Calibration(**settings, alpha_real=alpha.real, alpha_imag=alpha.imag,
                       trial_mass_g=mass, trial_radius_mm=radius, trial_angle_deg=angle,
                       created_at=datetime.now(timezone.utc).isoformat()).validate()


# --------------------------------------
# Corrección del desbalance a partir del α
# --------------------------------------

def correction(measurement, calibration, radius):
    # Invierte el modelo: a partir de una medición en funcionamiento calcula masa y ángulo de corrección.
    calibration.validate()
    positive(radius, 'Radio de corrección')
    positive(measurement.rpm, 'RPM')
    if abs(measurement.rpm - calibration.target_rpm) / calibration.target_rpm * 100 > calibration.tolerance_pct:
        raise ValueError('La velocidad no corresponde a la calibración.')
    # El vector de desbalance corregido es el opuesto del vector observado dividido entre el coeficiente de influencia.
    u = -measurement.vector / calibration.alpha
    return {'mass_g': abs(u) / radius, 'unbalance_gmm': abs(u),
            'angle_deg': (calibration.phase_sign * math.degrees(cmath.phase(u))) % 360}


# ---------------------------------------------------
# Distribución de una masa equivalente sobre varios álabes
# ---------------------------------------------------

def distribute_on_blades(mass_g, angle_deg, blades, blade_one_deg=0.0):
    """Distribuye una masa equivalente entre álabes vecinos y equiespaciados a igual radio.

    Los ángulos aumentan en la dirección física almacenada en la calibración.
    Devuelve tuplas (número de álabe, masa en g, ángulo físico en grados).
    """
    # Valida la cantidad de álabes y la consistencia de la entrada geométrica.
    if not isinstance(blades, int) or isinstance(blades, bool) or blades < 1:
        raise ValueError('Número de álabes inválido.')
    if not all(math.isfinite(v) for v in (mass_g, angle_deg, blade_one_deg)) or mass_g < 0:
        raise ValueError('Masa o ángulo inválido.')
    if mass_g == 0:
        return []

    # El paso angular indica la separación entre álabes consecutivos.
    step = 360.0 / blades
    position = ((angle_deg - blade_one_deg) % 360) / step
    nearest = round(position)
    if abs(position - nearest) < 1e-9:
        # Si la masa está exactamente alineada con un álabe, se coloca toda en ese punto.
        index = nearest % blades
        return [(index + 1, mass_g, (blade_one_deg + index * step) % 360)]
    if blades < 3:
        raise ValueError('Con uno o dos álabes no se puede reproducir este ángulo mediante masas agregadas. Usa una posición de corrección libre.')

    # Cuando cae entre dos álabes, se distribuye en dos masas adyacentes para reproducir la resultante vectorial.
    index = math.floor(position)
    delta = math.radians((position - index) * step)
    separation = math.radians(step)
    first = mass_g * math.sin(separation - delta) / math.sin(separation)
    second = mass_g * math.sin(delta) / math.sin(separation)
    return [(index + 1, first, (blade_one_deg + index * step) % 360),
            ((index + 1) % blades + 1, second, (blade_one_deg + (index + 1) * step) % 360)]
