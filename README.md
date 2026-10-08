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

## Vista Polar 1X

En el área gráfica, las pestañas **Señal temporal** y **Polar 1X** seleccionan la
visualización activa. En la polar, el radio representa la amplitud 1X en volts y
el ángulo la fase respecto al cruce ascendente del trigger. Se utiliza 0° a la
derecha y sentido antihorario. No es una indicación de masa de corrección.

La escala radial es fija y ajustable (1 V por defecto); si la amplitud excede el
máximo se muestra un aviso. El vector se oculta cuando el análisis no dispone
de una revolución utilizable o de amplitud 1X finita y positiva. Esta comprobación
no certifica la calidad del trigger ni establece un umbral contra ruido.

La adquisición y el análisis continúan al cambiar de pestaña. La vista temporal
se actualiza cada 33 ms; su temporizador se detiene en la pestaña polar, evitando
la extracción y conversión de muestras destinadas al dibujo. La polar se
actualiza con los resultados del análisis (hasta aproximadamente 10 Hz).
La cuadrícula se reconstruye únicamente al cambiar la escala radial.

Cambios: `app.py`, `theme.py`, `analysis_core.py` y nuevo `polar_plot.py`.
`phase_valid` se añade al resultado del análisis sin cambiar el cálculo de 1X.
Validado con simulador, retorno entre pestañas, ausencia de actualización del
osciloscopio oculto, fase inválida, amplitud fuera de escala y pruebas del núcleo.
No se ha medido CPU/memoria ni validado con hardware o Windows.

## Calibración y prueba de balanceo en un plano

La pestaña **Balanceo · 1 plano** contiene el flujo de **Calibración**.
La **Prueba de balanceo** está en **Polar 1X**, junto a la gráfica: cargar
calibración, definir radio y límite, medir y verificar. El separador permite
ajustar el espacio de cada panel; en ventanas estrechas se apilan verticalmente.
Los controles de adquisición siguen disponibles. Fuera de la vista temporal se
detiene el dibujo del osciloscopio; la adquisición y el análisis siguen activos. Los resultados de trabajo se capturan mediante botones; no se modifica
continuamente una recomendación que ya fue capturada.

### Calibración

1. Conectar la fuente y configurar ADC full-scale y umbral del trigger.
2. Abrir Balanceo · 1 plano y definir perfil/montaje, marca física de 0°, sentido de
   los ángulos, respuesta angular y RPM nominales.
3. Capturar el rotor **sin masa de prueba**.
4. Detener el rotor, colocar una masa conocida a un radio y ángulo conocidos,
   introducir esos valores y capturar **con masa de prueba** a las mismas RPM.
5. Calcular y guardar un archivo `.json`. El archivo conserva coeficiente complejo,
   configuración, convención angular, masa de prueba y fecha. Puede cargarse en
   otra sesión mediante **Cargar calibración**.
6. Retirar la masa de prueba antes de utilizar el modo de prueba.

La relación angular requiere validación física. En **Fase aumenta con el ángulo**,
la fase del cambio de vibración aumenta al mover la masa en el sentido positivo
seleccionado; la otra opción representa el signo inverso. Una única masa en una
única posición no identifica este signo. Puede comprobarse comparando el cambio
vectorial respecto al rotor inicial al colocar la misma masa en dos posiciones
conocidas. La polar de medición conserva su convención de pantalla; los ángulos
físicos de corrección utilizan la convención guardada en la calibración.

`alpha = (V_con_masa - V_inicial) / (m_prueba * r_prueba * exp(j * signo * angulo))`.
La unidad de alpha es V/(g·mm). Su cálculo rechaza una respuesta menor o igual a
5 veces la dispersión combinada, al 5% de la mayor amplitud capturada o a 1 µV,
según el mayor de esos límites. Los parámetros de estabilidad son provisionales;
deben ajustarse después de caracterizar la repetibilidad del equipo real.

### Prueba de balanceo

Abrir **Polar 1X**. Al cargar o guardar una calibración se abre automáticamente
esta pestaña. La gráfica continúa mostrando la vibración 1X medida en volts;
la recomendación de masa y ángulo físico aparece en el panel de prueba.

1. Cargar una calibración compatible y confirmar físicamente el perfil, montaje,
   referencia angular y velocidad indicados. El programa no detecta la identidad
   del rotor, cambios mecánicos ni cambios de ganancia externos.
2. Definir el radio de corrección en el mismo plano y, si existe, el límite
   permitido de desbalance residual en g·mm. Un límite de cero significa que no
   se ha definido un criterio de aceptación.
3. Pulsar **Medir rotor y calcular corrección**. Se indica masa a **agregar**, ángulo,
   sentido y radio, junto con el reparto equivalente entre álabes vecinos.
4. Detener el rotor, colocar la masa y volver a girar. Pulsar **Verificar** para
   medir el desbalance residual estimado, reducción de amplitud y corrección
   adicional estimada. Mantener las correcciones ya instaladas.
5. Pulsar **Nueva pieza** para limpiar los resultados de la pieza anterior.

`U_c = -V / alpha`; `m_c = abs(U_c) / r_c`; el ángulo físico se obtiene aplicando
el signo guardado al argumento de U_c. El radio de corrección puede cambiar en
el mismo plano, porque alpha se expresa por unidad de desbalance (g·mm).

### Capturas, compatibilidad y límites de esta versión

- Cada captura toma tres ventanas nuevas de 2 s sin solapamiento (~6 s o más).
  Se promedian vectores complejos, no ángulos directamente.
- Se requieren fase válida y al menos tres revoluciones por ventana. Se verifica
  RPM nominal y variación vectorial (valores iniciales: 2% y 10%).
- La captura se cancela ante desconexión, ausencia de datos recientes, errores
  CRC/ADC/pérdida de secuencia, cambio de configuración o tiempo máximo de 30 s.
- No se pueden utilizar calibraciones de simulador con una fuente serie y viceversa.
  ADC full-scale, frecuencia de muestreo y umbral deben coincidir con el archivo.
- El simulador original produce una señal fija: no modela una masa de prueba ni
  masas de corrección. Dos capturas iguales deben rechazar la calibración. Las
  pruebas automáticas utilizan vectores sintéticos con respuesta conocida para
  verificar el cálculo y la persistencia.
- La aceptación utiliza el límite de g·mm introducido. No se aplica un grado ISO
  automáticamente ni se calibra la velocidad de vibración en mm/s.
- Se asume respuesta lineal de un solo plano. La validación física de referencia,
  signo angular, sensibilidad y respuesta residual está pendiente.

Comprobaciones:

```bash
python test_core.py
python test_calibration.py
# Linux sin pantalla:
QT_QPA_PLATFORM=offscreen python test_workflow.py
# En Windows, también puede ejecutarse con una ventana visible:
python test_workflow.py
```

Las capturas `previews/calibration-*.png` y `previews/balancing-*.png` ilustran el
flujo con datos sintéticos de demostración. No son una calibración física válida.

## Colocación de masas por álabes

En **Polar 1X**, la prueba utiliza el **N.º álabes** de Configuración de señal.
Define **Ángulo del álabe 1** respecto a la misma marca física de 0° usada al
calibrar. Los álabes se numeran del 1 al N en el sentido angular guardado en la
calibración, observando siempre desde el mismo lado. Este ángulo de numeración
no modifica la referencia del trigger ni el coeficiente.

Se supone que los álabes son equidistantes y que todas las masas se colocan en
el mismo plano y radio indicado. La pantalla muestra el vector de corrección
continuo y la masa a agregar en cada uno de los dos álabes vecinos. Cuando la
posición coincide con un álabe, se indica una sola masa. El reparto también se
aplica a la corrección adicional estimada después de verificar el residual.
La gráfica polar sigue representando vibración 1X en volts, no masas en gramos.

Para separación angular D=360/N y una corrección situada a d del primer álabe:

`m1 = m * sin(D-d) / sin(D)`

`m2 = m * sin(d) / sin(D)`

Las masas se suman vectorialmente; su suma aritmética puede superar la masa
continua equivalente. Cambiar el número de álabes, el ángulo del álabe 1 o el radio
recalcula la indicación a partir de la misma medición capturada.

Con uno o dos álabes solo puede colocarse exactamente una corrección alineada
con uno de ellos; otros ángulos requieren una posición libre de corrección.
Para álabes no equidistantes o radios diferentes se necesita otro modelo de
posiciones. Las pruebas verifican reconstrucción vectorial, cruce 360°/0°,
coincidencia exacta, numeración y actualización del resultado en la interfaz.
