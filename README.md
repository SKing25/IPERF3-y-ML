# Laboratorio de Análisis de Datos en Redes
## Predicción de Congestión en un Enlace LAN: Captura de Tráfico y Regresión Lineal

Este repositorio contiene la solución completa y reproducible del **Laboratorio de Análisis de Datos en Redes** especificado en el documento `Taller_Análisis_Datos.pdf`.

---

### 1. Topología y Montaje Experimental

El montaje conecta dos máquinas bajo Linux comunicándose mediante UDP:

```text
+-----------------------------------+               +-----------------------------------+
|      COMPUTADOR A (Emisor)        |               |      COMPUTADOR B (Receptor)      |
|           Host Linux              |               |         Máquina Virtual           |
|         192.168.50.10/24          |               |         192.168.50.20/24          |
|                                   |               |                                   |
|  * Cliente iperf3 (UDP port 5201) |               |  * Servidor iperf3                |
|  * Cola TBF de salida (10 Mbit/s) |   Ethernet    |    (iperf3 -s)                    |
|  * Captura tcpdump (PCAP)         | ------------> |                                   |
|  * Muestreo de cola (tc -j -s)    |               |                                   |
|  * Procesamiento y Regresión ML   |               |                                   |
+-----------------------------------+               +-----------------------------------+
```

- **Computador A (Host Linux)**: Es el emisor del tráfico, el punto de control donde se aplica la disciplina de cola TBF (`tc`), se capturan los paquetes con `tcpdump`, se muestrean los descartes de cola con `tc` y se ejecuta todo el pipeline de análisis de datos y machine learning.
- **Computador B (VM Linux)**: Es el receptor del tráfico, actúa como servidor de pruebas ejecutando `iperf3 -s`.

---

### 2. Estructura de Scripts y Archivos

```text
IPERF3 y ML/
├── 01_configurar_red_y_cola.sh    # Script de configuración de IP y cola TBF en A
├── 02_ejecutar_corrida.py         # Orquestador automatizado de capturas y tráfico UDP (c01..c06)
├── 03_procesar_trazas.py          # Extractor PCAP, alineador temporal de ventanas (~1s) y rezagos
├── 04_entrenar_evaluar.py         # Ajuste de Regresión Lineal, calibración en Val, métricas en Test y gráficas
├── 00_simular_corridas_demo.py    # Simulador sintético del enlace TBF para pruebas rápidas
├── datos/                         # Almacenamiento organizado por corrida (c01 a c06)
│   ├── c01/ .. c06/               # Archivos .pcap, _cola.log, _faseXX.json, _paquetes.csv, _ventanas.csv
│   └── dataset_completo_ventanas.csv
├── resultados/                    # Gráficas temporales de 3 paneles e informe de métricas
│   ├── grafica_temporal_c05.png
│   ├── grafica_temporal_c06.png
│   └── informe_metricas.txt
└── README.md
```

---

### 3. Guía Paso a Paso para la Realización del Taller

#### Paso 1: Configurar las Direcciones IP

**En Computador B (Máquina Virtual Linux):**
1. Identifica el nombre de la interfaz de red (por ejemplo `enp0s3` o `eth0`):
   ```bash
   ip -br addr
   ```
2. Asigna la IP fija solicitada en el taller:
   ```bash
   sudo ip addr add 192.168.50.20/24 dev <nombre_interfaz_vm>
   ```
3. Permite el tráfico en el puerto UDP 5201 si tienes firewall:
   ```bash
   sudo ufw allow 5201/udp
   ```
4. Deja el servidor `iperf3` en ejecución:
   ```bash
   iperf3 -s
   ```

**En Computador A (Host Linux):**
1. Identifica tu interfaz de red conectada a la VM (por defecto `eno1`):
   ```bash
   ip -br addr
   ```
2. Ejecuta el script de configuración automática:
   ```bash
   ./01_configurar_red_y_cola.sh eno1
   ```
   *(Este comando agrega la IP `192.168.50.10/24` y configura la disciplina de cola TBF a 10 Mbit/s)*.
3. Verifica la conectividad con la VM:
   ```bash
   ping -c 3 192.168.50.20
   ```

---

#### Paso 2: Ejecutar las Corridas Experimentales (c01 a c06)

El taller requiere adquirir **al menos 6 corridas independientes** variando perfiles de carga (rampas graduales, saltos bruscos a sobrecarga y pausas de recuperación).

Para ejecutar cada corrida de manera sincronizada y desatendida, ejecuta en el Computador A:

```bash
# Corrida 1: Rampas y sobrecargas (Entrenamiento)
sudo python3 02_ejecutar_corrida.py --corrida c01

# Corrida 2: Saltos bruscos repentinos (Entrenamiento)
sudo python3 02_ejecutar_corrida.py --corrida c02

# Corrida 3: Rampas progresivas y pico severo (Entrenamiento)
sudo python3 02_ejecutar_corrida.py --corrida c03

# Corrida 4: Mixta rampa y escalones (Validación)
sudo python3 02_ejecutar_corrida.py --corrida c04

# Corrida 5: Salto temprano + rampa tardía (Prueba 1)
sudo python3 02_ejecutar_corrida.py --corrida c05

# Corrida 6: Doble episodio con intensidades distintas (Prueba 2)
sudo python3 02_ejecutar_corrida.py --corrida c06
```

> **Nota:** Si antes de realizar las pruebas físicas deseas probar todo el software y la generación de gráficos, puedes ejecutar `python3 00_simular_corridas_demo.py` para generar datos sintéticos realistas basados en las ecuaciones del cuello de botella TBF.

---

#### Paso 3: Procesar Trazas y Construir la Serie Temporal

Una vez obtenidas las capturas, ejecuta:

```bash
python3 03_procesar_trazas.py
```

Este script:
1. Extrae los paquetes capturados (`frame.time_epoch,frame.len`) usando `tshark` o el extractor binario nativo en Python.
2. Analiza los logs de cola `tc -j -s` y extrae los descartes acumulados $D(t_k)$.
3. Alinea temporalmente las ventanas $[t_{k-1}, t_k)$ de duración real $\Delta_k \approx 1$ s.
4. Calcula:
   $$r_k = \frac{8 B_k}{10^6 \Delta_k} \quad (\text{Mbit/s}), \qquad d_k = D(t_k) - D(t_{k-1})$$
5. Construye los rezagos $r_{k-1}$, $r_{k-2}$ y el objetivo $y_k = d_{k+1}$.
6. Genera `datos/dataset_completo_ventanas.csv`.

---

#### Paso 4: Entrenar el Modelo y Evaluar Alertas

Ejecuta el script de Machine Learning:

```bash
python3 04_entrenar_evaluar.py
```

Este script realiza:
1. **Partición Estricta:**
   - Entrenamiento: Corridas `c01`, `c02`, `c03`.
   - Validación: Corrida `c04`.
   - Prueba: Corridas `c05`, `c06`.
2. **Ajuste del Modelo:**
   $$\hat{y}_k = \beta_0 + \beta_1 r_k + \beta_2 r_{k-1} + \beta_3 r_{k-2} + \beta_4 n_k$$
   Llevando las predicciones negativas a cero: $\hat{y}_k = \max(0, \hat{y}_k)$.
3. **Calibración de Alertas en Validación (`c04`):**
   - Regresión Lineal: Alerta si $\hat{y}_k \geq \text{umbral}$.
   - Regla Simple de Tasa: Alerta si $r_k \geq \text{umbral\_tasa}$.
4. **Evaluación en Prueba (`c05` y `c06`):**
   - MAE en paquetes por ventana.
   - Matriz de confusión, Precisión, Sensibilidad (Recall), Especificidad y F1-Score.
   - **Distinción entre Inicio y Persistencia:** Medición de cuántos inicios ($d_k=0 \to d_{k+1}>0$) fueron anticipados antes de que ocurrieran vs cuántos fueron omitidos.
5. **Generación de Gráficas Temporales de 3 Paneles:**
   - Panel 1: Tasa capturada $r_k$ (Mbit/s) vs Capacidad (10 Mbit/s).
   - Panel 2: Descartes reales $d_{k+1}$ vs Pronosticados $\hat{y}_k$.
   - Panel 3: Alertas emitidas vs Congestión real observada, con marcadores de inicio anticipado/omitido.

---

#### Paso 5: Restauración de la Interfaz (Al finalizar el laboratorio)

Para remover la cola TBF y restaurar la configuración original de red:
```bash
sudo tc qdisc del dev eno1 root
```
Y si deseas eliminar la IP virtual asignada:
```bash
sudo ip addr del 192.168.50.10/24 dev eno1
```
