# Resumen del Informe de Laboratorio: Análisis de Datos en Redes
## Predicción de Congestión en un Enlace LAN mediante Captura de Tráfico y Regresión Lineal

Este documento resume los resultados obtenidos en el laboratorio y sirve de referencia al informe en LaTeX generado en [docs/informe.pdf](file:///home/santiago/Documentos/Codigos/IPERF3 y ML/docs/informe.pdf).

---

### 1. Resumen Ejecutivo
Se implementó un banco de pruebas experimental bajo Linux compuesto por un emisor (**Host Linux**) y un receptor (**Máquina Virtual Linux**). Se forzó un cuello de botella con la disciplina de cola Token Bucket Filter (**TBF**) a **10 Mbit/s** (ráfaga 16 KB, límite 32 KB). Se generó tráfico UDP mediante `iperf3` sobre el puerto 5201 en datagramas de 1200 bytes a lo largo de 6 corridas continuas (`c01` a `c06`).

A partir de la captura continua de tramas (`tcpdump`) y del muestreo sincrónico de descartes en el kernel (`tc -j -s`), se discretizó la serie temporal en ventanas de $\Delta_k \approx 1$ s. Se entrenó un estimador de **Regresión Lineal** ordinaria con rezagos temporales ($r_k, r_{k-1}, r_{k-2}, n_k$) para pronosticar los descartes de la siguiente ventana ($y_k = d_{k+1}$) y emitir alertas tempranas.

---

### 2. Resultados Clave y Métricas en Prueba (`c05` y `c06`)

* **Dataset total procesado:** 825 ventanas reales de 1 segundo (322 ventanas con congestión $d_k \ge 1$).
* **Modelo ajustado:**
  $$\hat{y}_k = -232.7216 - 87.1296\,r_k - 0.8435\,r_{k-1} + 12.3662\,r_{k-2} + 1.4062\,n_k$$
  con $\hat{y}_k = \max(0, \hat{y}_k)$ y $\text{MAE} = 154.38$ paquetes/ventana.
* **Calibración en Validación (`c04`):**
  - Umbral Regresión Lineal: $\hat{y}_k \ge 0.50$
  - Umbral Regla Simple de Tasa: $r_k \ge 8.50$ Mbit/s

#### Comparación de Clasificación de Alertas:
| Métrica | Regresión Lineal | Regla Simple de Tasa |
| :--- | :---: | :---: |
| **Verdaderos Positivos (TP)** | 110 | 104 |
| **Falsos Positivos (FP)** | 135 | 20 |
| **Verdaderos Negativos (TN)** | 51 | 166 |
| **Falsos Negativos (FN)** | **3** | 9 |
| **Sensibilidad / Recall** | **97.35%** | 92.04% |
| **Precisión** | 44.90% | **83.87%** |
| **F1-Score** | 0.6145 | **0.8776** |

#### Distinción entre Inicio y Persistencia:
* **Inicios observados ($d_k = 0 \to d_{k+1} > 0$):** 4 episodios.
* **Tasa de Anticipación de Inicios (Regresión):** **50.0%** (2 de 4 inicios anticipados).
* **Tasa de Anticipación (Regla Simple):** **0.0%** (0 de 4 inicios anticipados).
* **Persistencia detectada ($d_k > 0 \to d_{k+1} > 0$):** 108 de 109 ventanas (99.1%).

---

### 3. Respuestas a las Preguntas de Discusión del Taller

1. **¿El modelo anticipó los inicios o tendió a reconocer episodios en curso?**
   - El modelo reconoce episodios en curso con un 99.1% de éxito. En cuanto a inicios, anticipó el 50.0% de ellos, mientras que la regla reactiva falló por completo (0.0%). Los rezagos temporales y el número de paquetes permiten detectar la aceleración del flujo antes de que se produzca el primer descarte.
2. **Rampas graduales vs Saltos bruscos:**
   - En rampas graduales, el encolamiento progresivo permite que el modelo alerte con 1 segundo de anticipación. En saltos bruscos (ej. de 4 a 15 Mbit/s), el búfer de 32 KB se llena en menos de 65 ms, lo que impide que la ventana previa refleje el colapso inminente.
3. **Falsa Alarma e Inicio Omitido:**
   - *Falsa Alarma (FP):* Ocurre en las fases de descompresión (cuando la tasa cae de 15 a 4 Mbit/s), donde los rezagos $r_{k-1}$ y $r_{k-2}$ aún conservan valores altos de la congestión anterior.
   - *Inicio Omitido (FN):* Ocurre en el primer segundo de un salto repentino sin historia previa.
4. **Limitación física de la predicción:**
   - La disparidad de escalas temporales: la telemetría muestrea cada $\Delta t \approx 1$ s, mientras que la física del búfer TBF satura en $\tau \approx 65$ ms ante sobrecarga.
