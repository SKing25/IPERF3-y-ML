#!/usr/bin/env bash
# ==============================================================================
# Laboratorio de Análisis de Datos en Redes: Predicción de Congestión en LAN
# Script 01: Configuración de Red e Interfaz (Computador A - Host)
# ==============================================================================

set -e

# Si no se pasó argumento, detectar si eno1 tiene cable o si usamos vboxnet0
if [ -z "$1" ]; then
    if ip link show vboxnet0 > /dev/null 2>&1 && ip link show eno1 | grep -q "NO-CARRIER"; then
        IFACE="vboxnet0"
        echo "[*] 'eno1' no tiene cable conectado (NO-CARRIER). Usando interfaz virtual 'vboxnet0'."
    else
        IFACE="eno1"
    fi
else
    IFACE="$1"
fi

echo "=========================================================="
echo " CONFIGURACIÓN DE RED Y COLA TBF EN COMPUTADOR A (EMISOR)"
echo "=========================================================="
echo "Interfaz seleccionada: $IFACE"
echo ""

# 1. Verificar si la interfaz existe
if ! ip link show "$IFACE" > /dev/null 2>&1; then
    echo "[-] ERROR: La interfaz '$IFACE' no existe."
    echo "    Revisa tus interfaces con: ip -br addr"
    exit 1
fi

# 2. Asignar IP 192.168.50.10/24 y levantar interfaz
CURRENT_IP=$(ip -4 addr show dev "$IFACE" | grep -o '192\.168\.50\.10/24' || true)
if [ -z "$CURRENT_IP" ]; then
    echo "[+] Asignando IP 192.168.50.10/24 a $IFACE..."
    sudo ip addr add 192.168.50.10/24 dev "$IFACE"
else
    echo "[*] La IP 192.168.50.10/24 ya está asignada a $IFACE."
fi
sudo ip link set dev "$IFACE" up

# 3. Mostrar configuración de cola original
echo ""
echo "[*] Configuración qdisc actual en $IFACE:"
tc qdisc show dev "$IFACE"

# 4. Configurar cuello de botella controlado con TBF (Token Bucket Filter):
#    rate 10mbit, burst 16kb, limit 32kb
echo ""
echo "[+] Configurando cuello de botella TBF (10 Mbit/s, burst 16kb, limit 32kb)..."
sudo tc qdisc replace dev "$IFACE" root handle 10: tbf rate 10mbit burst 16kb limit 32kb

# 5. Verificar estado de la cola
echo ""
echo "[+] Estado del qdisc configurado:"
tc -s qdisc show dev "$IFACE"

echo ""
echo "=========================================================="
echo " RESUMEN Y PASOS SIGUIENTES"
echo "=========================================================="
echo "1. En la Máquina Virtual (Computador B):"
echo "   - Averigua el nombre de su interfaz: ip -br addr"
echo "   - Asigna su IP: sudo ip addr add 192.168.50.20/24 dev <interfaz_vm>"
echo "   - Prueba conectividad: ping 192.168.50.10"
echo "   - Inicia el servidor iperf3: iperf3 -s"
echo ""
echo "2. Desde este Computador (A):"
echo "   - Prueba conectividad: ping 192.168.50.20"
echo "   - Luego ejecuta las corridas con: python3 02_ejecutar_corrida.py --corrida c01"
echo ""
echo "Nota: Si al terminar el laboratorio deseas eliminar el límite TBF:"
echo "      sudo tc qdisc del dev $IFACE root"
echo "=========================================================="
