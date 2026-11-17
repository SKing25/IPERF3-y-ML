#!/usr/bin/env python3
"""
Laboratorio de Análisis de Datos en Redes: Predicción de Congestión en LAN
Script 02: Ejecutor Automatizado de Corridas Experimentales (Computador A)

Orquesta de forma sincronizada:
1. Captura continua con tcpdump en segundo plano (archivo .pcap).
2. Muestreo continuo de la cola TBF con tc -j -s (archivo _cola.log).
3. Generación de tráfico UDP por fases con iperf3 (archivos _faseXX.json).
"""

import argparse
import json
import os
import signal
import subprocess
import sys
import time

PERFILES_CORRIDAS = {
    "c01": [
        {"nombre": "Base", "tasa": 4, "duracion": 20, "proposito": "Medir con carga baja"},
        {"nombre": "Ascenso", "tasa": 8, "duracion": 20, "proposito": "Aproximarse al límite"},
        {"nombre": "Sobrecarga", "tasa": 14, "duracion": 20, "proposito": "Provocar descartes"},
        {"nombre": "Recuperacion", "tasa": 5, "duracion": 20, "proposito": "Fin del primer episodio"},
        {"nombre": "Sobrecarga_2", "tasa": 16, "duracion": 20, "proposito": "Segundo episodio severo"},
        {"nombre": "Fin", "tasa": 4, "duracion": 20, "proposito": "Estabilización final"}
    ],
    "c02": [
        {"nombre": "Base", "tasa": 4, "duracion": 20, "proposito": "Carga baja inicial"},
        {"nombre": "Salto_Brusco_1", "tasa": 15, "duracion": 25, "proposito": "Salto brusco a sobrecarga"},
        {"nombre": "Recuperacion", "tasa": 4, "duracion": 20, "proposito": "Retorno a la normalidad"},
        {"nombre": "Salto_Brusco_2", "tasa": 16, "duracion": 25, "proposito": "Segundo salto brusco a sobrecarga"},
        {"nombre": "Fin", "tasa": 3, "duracion": 15, "proposito": "Reposo"}
    ],
    "c03": [
        {"nombre": "Base", "tasa": 5, "duracion": 15, "proposito": "Medir línea base"},
        {"nombre": "Rampa_1", "tasa": 7, "duracion": 15, "proposito": "Ascenso progresivo nivel 1"},
        {"nombre": "Rampa_2", "tasa": 9, "duracion": 15, "proposito": "Ascenso progresivo nivel 2"},
        {"nombre": "Sobrecarga", "tasa": 13, "duracion": 25, "proposito": "Sobrecarga sostenida"},
        {"nombre": "Recuperacion", "tasa": 5, "duracion": 20, "proposito": "Descenso"},
        {"nombre": "Sobrecarga_Pico", "tasa": 17, "duracion": 20, "proposito": "Pico máximo de sobrecarga"},
        {"nombre": "Fin", "tasa": 4, "duracion": 15, "proposito": "Cierre"}
    ],
    "c04": [
        {"nombre": "Base", "tasa": 4, "duracion": 15, "proposito": "Base (Validación)"},
        {"nombre": "Rampa", "tasa": 8, "duracion": 15, "proposito": "Aproximación gradual"},
        {"nombre": "Sobrecarga_Mod", "tasa": 12, "duracion": 20, "proposito": "Sobrecarga moderada"},
        {"nombre": "Sobrecarga_Fuerte", "tasa": 16, "duracion": 20, "proposito": "Sobrecarga fuerte"},
        {"nombre": "Recuperacion", "tasa": 5, "duracion": 20, "proposito": "Recuperación"},
        {"nombre": "Salto_Brusco", "tasa": 15, "duracion": 25, "proposito": "Salto brusco"},
        {"nombre": "Fin", "tasa": 4, "duracion": 15, "proposito": "Estabilización"}
    ],
    "c05": [
        {"nombre": "Base", "tasa": 4, "duracion": 20, "proposito": "Base (Prueba 1)"},
        {"nombre": "Salto_Brusco", "tasa": 14, "duracion": 25, "proposito": "Salto repentino"},
        {"nombre": "Recuperacion", "tasa": 5, "duracion": 20, "proposito": "Recuperación"},
        {"nombre": "Rampa_1", "tasa": 7, "duracion": 15, "proposito": "Rampa escalonada 1"},
        {"nombre": "Rampa_2", "tasa": 10, "duracion": 15, "proposito": "Rampa escalonada 2 (al límite)"},
        {"nombre": "Rampa_Sobrecarga", "tasa": 15, "duracion": 20, "proposito": "Culminación rampa sobrecarga"},
        {"nombre": "Fin", "tasa": 4, "duracion": 20, "proposito": "Fin"}
    ],
    "c06": [
        {"nombre": "Base", "tasa": 3, "duracion": 15, "proposito": "Base (Prueba 2)"},
        {"nombre": "Rampa_Suave_1", "tasa": 6, "duracion": 20, "proposito": "Rampa suave"},
        {"nombre": "Rampa_Suave_2", "tasa": 9, "duracion": 20, "proposito": "Cerca del límite de 10 Mbit/s"},
        {"nombre": "Sobrecarga_Frontera", "tasa": 11, "duracion": 25, "proposito": "Descartes moderados frontera"},
        {"nombre": "Recuperacion", "tasa": 4, "duracion": 20, "proposito": "Recuperación intermedia"},
        {"nombre": "Sobrecarga_Severa", "tasa": 17, "duracion": 25, "proposito": "Descartes masivos"},
        {"nombre": "Fin", "tasa": 3, "duracion": 15, "proposito": "Reposo final"}
    ]
}


def verificar_conectividad(servidor_ip):
    print(f"[*] Verificando conectividad con servidor {servidor_ip}...")
    res = subprocess.run(["ping", "-c", "2", "-W", "2", servidor_ip],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if res.returncode != 0:
        print(f"[-] ADVERTENCIA: No se recibe ping de {servidor_ip}.")
        print("    Asegúrate de que la VM tenga asignada la IP 192.168.50.20/24")
        resp = input("    ¿Deseas continuar de todos modos? (s/n): ").strip().lower()
        if resp != 's':
            sys.exit(1)
    else:
        print(f"[+] Conectividad con {servidor_ip} confirmada.")


def main():
    parser = argparse.ArgumentParser(description="Ejecutor de corrida experimental para taller de análisis de datos.")
    parser.add_argument("--corrida", required=True, help="Identificador de la corrida (ej. c01, c02, ..., c06)")
    parser.add_argument("--iface", default=None, help="Nombre de la interfaz en A (default: auto-detectar entre eno1 y vboxnet0)")
    parser.add_argument("--servidor", default="192.168.50.20", help="IP del servidor B (default: 192.168.50.20)")
    parser.add_argument("--emisor", default="192.168.50.10", help="IP del emisor A (default: 192.168.50.10)")
    parser.add_argument("--salida-dir", default="datos", help="Directorio base para guardar datos (default: datos)")
    args = parser.parse_args()

    # Detección automática de interfaz
    iface = args.iface
    if not iface:
        try:
            out = subprocess.check_output(["ip", "-o", "-4", "addr", "list"], text=True)
            for line in out.splitlines():
                if args.emisor in line:
                    iface = line.split()[1]
                    break
        except Exception:
            pass
        if not iface:
            iface = "vboxnet0" if os.path.exists("/sys/class/net/vboxnet0") else "eno1"
    args.iface = iface

    corrida = args.corrida.lower()
    if corrida not in PERFILES_CORRIDAS:
        print(f"[-] Corrida desconocida '{corrida}'. Las opciones preconfiguradas son: {list(PERFILES_CORRIDAS.keys())}")
        sys.exit(1)

    fases = PERFILES_CORRIDAS[corrida]
    carpeta_corrida = os.path.join(args.salida_dir, corrida)
    os.makedirs(carpeta_corrida, exist_ok=True)

    verificar_conectividad(args.servidor)

    pcap_path = os.path.join(carpeta_corrida, f"{corrida}.pcap")
    cola_log_path = os.path.join(carpeta_corrida, f"{corrida}_cola.log")

    print("\n" + "="*60)
    print(f" INICIANDO CORRIDA: {corrida.upper()}")
    print("="*60)
    print(f"  * Interfaz: {args.iface}")
    print(f"  * Emisor A: {args.emisor}")
    print(f"  * Receptor B: {args.servidor}")
    print(f"  * PCAP: {pcap_path}")
    print(f"  * Log Cola: {cola_log_path}")
    print(f"  * Total fases: {len(fases)}")
    print("="*60 + "\n")

    # 1. Iniciar tcpdump
    filtro = f"src host {args.emisor} and dst host {args.servidor} and udp dst port 5201"
    cmd_tcpdump = [
        "sudo", "tcpdump", "-i", args.iface,
        "-nn", "-s", "96", "-B", "4096",
        "-w", pcap_path,
        filtro
    ]
    print(f"[+] Iniciando captura tcpdump -> {pcap_path}")
    proc_tcpdump = subprocess.Popen(cmd_tcpdump, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)

    # 2. Iniciar bucle de muestreo de cola tc
    print(f"[+] Iniciando muestreo continuo de cola TBF -> {cola_log_path}")
    bucle_script = (
        f"while true; do "
        f"date +%s.%N; "
        f"tc -j -s qdisc show dev {args.iface} || break; "
        f"sleep 1; "
        f"done > '{cola_log_path}'"
    )
    proc_cola = subprocess.Popen(["bash", "-c", bucle_script], preexec_fn=os.setsid)

    # Pausa de línea base previa al tráfico (5 segundos)
    print("[*] Registrando línea base de reposo antes del tráfico (5s)...")
    time.sleep(5)

    try:
        # 3. Ejecutar las fases de iperf3
        calendario_log = os.path.join(carpeta_corrida, f"{corrida}_calendario.txt")
        with open(calendario_log, "w", encoding="utf-8") as f_cal:
            f_cal.write(f"Corrida: {corrida}\n")
            f_cal.write("Fase,Nombre,Tasa_Mbps,Duracion_s,Timestamp_Inicio,Proposito\n")

            for idx, f in enumerate(fases, start=1):
                fase_id = f"fase{idx:02d}"
                nombre = f["nombre"]
                tasa = f["tasa"]
                dur = f["duracion"]
                proposito = f["proposito"]
                json_path = os.path.join(carpeta_corrida, f"{corrida}_{fase_id}.json")

                ts_inicio = time.time()
                print(f"\n--- [Fase {idx}/{len(fases)}: {nombre}] ---")
                print(f"    Tasa: {tasa} Mbit/s | Duración: {dur}s | Propósito: {proposito}")

                cmd_iperf = [
                    "iperf3", "-c", args.servidor,
                    "-u", "-b", f"{tasa}M",
                    "-l", "1200",
                    "-t", str(dur),
                    "-i", "1",
                    "--get-server-output",
                    "-J"
                ]

                with open(json_path, "w") as out_f:
                    subprocess.run(cmd_iperf, stdout=out_f, stderr=subprocess.PIPE, check=False)

                f_cal.write(f"{fase_id},{nombre},{tasa},{dur},{ts_inicio:.3f},{proposito}\n")
                f_cal.flush()

                # Pausa corta opcional entre fases (1s)
                time.sleep(1)

        # Pausa de recuperación posterior al tráfico (5 segundos)
        print("\n[*] Registrando línea base de recuperación tras el tráfico (5s)...")
        time.sleep(5)

    except KeyboardInterrupt:
        print("\n[-] Interrupción detectada por el usuario (Ctrl+C). Deteniendo procesos...")
    finally:
        # Detener procesos en segundo plano limpiamente
        print("[*] Deteniendo muestreador de cola...")
        try:
            os.killpg(os.getpgid(proc_cola.pid), signal.SIGTERM)
        except Exception:
            pass

        print("[*] Deteniendo tcpdump...")
        tcpdump_stderr_content = b""
        try:
            # Enviar SIGINT (-2) a tcpdump para que imprima sus estadísticas en stderr
            subprocess.run(["sudo", "pkill", "-2", "-f", f"tcpdump.*{corrida}.pcap"], check=False)
            time.sleep(0.5)
            try:
                _, tcpdump_stderr_content = proc_tcpdump.communicate(timeout=3)
            except Exception:
                proc_tcpdump.kill()
                _, tcpdump_stderr_content = proc_tcpdump.communicate()
        except Exception as e:
            print(f"[-] Advertencia al detener tcpdump: {e}")

        # Guardar estadísticas de descarte por kernel de tcpdump
        tcpdump_log_path = os.path.join(carpeta_corrida, f"{corrida}_tcpdump.log")
        with open(tcpdump_log_path, "wb") as f_tcp_log:
            if tcpdump_stderr_content:
                f_tcp_log.write(tcpdump_stderr_content)
                print(f"[+] Resumen de captura tcpdump registrado en: {os.path.basename(tcpdump_log_path)}")
                print(tcpdump_stderr_content.decode(errors="replace").strip())
            else:
                f_tcp_log.write(b"tcpdump: stderr no capturado (requiere lectura de descriptores de proceso al terminar)\n")
                print("[-] Advertencia: No se capturaron líneas de stderr de tcpdump para esta corrida.")

    print("\n[+] Estado final de la cola TBF en la interfaz:")
    subprocess.run(["tc", "-s", "qdisc", "show", "dev", args.iface], check=False)

    print("\n" + "="*60)
    print(f" CORRIDA {corrida.upper()} COMPLETADA")
    print(f" Archivos generados en: {carpeta_corrida}/")
    print(f"   - PCAP: {os.path.basename(pcap_path)}")
    print(f"   - Log cola: {os.path.basename(cola_log_path)}")
    print(f"   - Calendario: {os.path.basename(calendario_log)}")
    print(f"   - JSONs iperf3: {len(fases)} archivos")
    print("="*60 + "\n")


if __name__ == "__main__":
    main()
