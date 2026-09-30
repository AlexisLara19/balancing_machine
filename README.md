# Vibration Scope v2

Base de aplicación PyQt6 para adquisición de vibración y trigger analógico desde PSoC 4.

## Parámetros implementados

- 2 canales analógicos.
- 2000 SPS por canal.
- ADC de 12 bits transmitido como `uint16` little-endian.
- 256 muestras por paquete y por canal.
- `0xAA` = canal de vibración.
- `0x55` = canal de trigger.
- CRC16-CCITT-FALSE.
- UART 115200 8N1.
- Payload separado por canal.
- Número de secuencia de 16 bits para sincronizar ambos canales.

## Formato de paquete

Cada paquete tiene 517 bytes:

```text
Byte 0        Header       0xAA o 0x55
Byte 1..2     Sequence     uint16 little-endian
Byte 3..514   Payload      256 x uint16 little-endian
Byte 515..516 CRC16        uint16 little-endian
```

El CRC se calcula sobre `Header + Sequence + Payload`.

Dos paquetes con el mismo `Sequence` forman un bloque completo de 256 muestras:

```text
0xAA + seq + CH1[256] + CRC
0x55 + seq + CH2[256] + CRC
```

## Arquitectura

```text
SerialReader / SimulatorReader (QThread)
                |
                v
        ProtocolWorker (QThread)
        parser + CRC + pairing
                |
                v
      DualChannelRingBuffer
          |             |
          v             v
   Oscilloscope     AnalysisWorker (QThread)
   ~30 FPS          RPM / fase / 1X / RMS
          \             /
           \           /
              PyQt6 GUI
```

La adquisición, el parser, el análisis y el renderizado están desacoplados.

## Simulador

Selecciona `SIMULATOR` como fuente y pulsa **Conectar**.

Genera:

- Vibración 1X de aproximadamente 125° respecto al trigger.
- Un segundo armónico débil y ruido.
- Trigger analógico sinusoidal.
- RPM configurables desde la GUI.
- El flujo binario real del protocolo, fragmentado en bloques arbitrarios para probar el parser incremental.

## Trigger / RPM

El trigger es analógico. Se detecta un cruce ascendente por un umbral configurable. Los cruces se interpolan linealmente entre muestras para obtener mejor resolución temporal que 0.5 ms.

Si hay un evento por revolución:

```text
RPM = 60 * Fs / muestras_por_revolución
```

## Fase

La fase 1X se obtiene usando los intervalos entre cruces consecutivos del trigger como referencias 0°..360°. Esto permite una forma básica de order tracking y evita depender exclusivamente de la FFT.

Convención actual:

```text
vibración ≈ A * cos(theta - fase)
```

El cruce ascendente del trigger define 0°.

Esta convención debe validarse físicamente con el sensor y un patrón conocido antes de usarla para indicar la posición de un peso de corrección.

## Conversión ADC a voltaje

Las muestras permanecen como `uint16` crudo en el buffer. La GUI convierte mediante:

```text
V = ADC * Vref / 4095
```

`Vref` es configurable porque aún debemos confirmar el rango real de entrada del ADC/acondicionador.

## Ejecutar

```bash
python -m venv .venv
.venv\\Scripts\\activate
pip install -r requirements.txt
python main.py
```

Prueba del núcleo:

```bash
python test_core.py
```

## Siguiente etapa recomendada

1. Confirmar `Vref` / rango analógico real de ambos canales.
2. Confirmar forma real de la señal de trigger y su umbral/histéresis.
3. Añadir histéresis/debounce al detector de trigger si hay ruido.
4. Convertir el canal de vibración desde volts a la unidad física del sensor, por ejemplo mm/s.
5. Validar fase y polaridad con una referencia física conocida.
6. Añadir FFT/espectro y análisis por órdenes en una vista secundaria.

## Apariencia de la interfaz

La primera revisión visual conserva los controles y el flujo de adquisición existentes.

- Paleta centralizada en `theme.py`: azul #004aad, fondo #e9ebed, paneles blancos y texto secundario #555f88.
- Tarjetas destacadas para RPM, amplitud 1X y fase; métricas complementarias bajo el osciloscopio.
- Vibración azul y trigger violeta (#8056ad), identificados también por su leyenda.
- Bordes suaves de 6–10 px; separación mediante bordes discretos, sin sombras sobre la gráfica.
- Panel de configuración desplazable y ventana mínima de 1080 × 720.
- Estilo Qt Fusion para una apariencia consistente entre plataformas.

Ejecutar con `python main.py`. Para ajustar colores, editar `COLORS` en `theme.py`.
Las capturas de `previews/` muestran datos del simulador, no mediciones físicas.

Validación: simulador a 1800 RPM, actualización de curvas y métricas, desconexión y cierre;
revisión visual a 1440 × 900 y 1080 × 720; prueba existente `python test_core.py`.
No se ha validado esta revisión con hardware conectado ni en Windows.
