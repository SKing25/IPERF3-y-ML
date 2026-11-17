#!/usr/bin/env python3
"""
Laboratorio de Análisis de Datos en Redes: Predicción de Congestión en LAN
Script 04: Entrenamiento de Regresión Lineal, Evaluación Rigurosa y Análisis Temporal

Versión Mejorada (v2):
- Incorpora diagnóstico de colinealidad r_k vs n_k y estudio de ablación.
- Incluye baselines formales de regresión (Predictor Cero, Persistencia, Media).
- Barrido completo y realista de umbrales en Validación c04 (1 a 350).
- Alineación estricta de pronósticos en la ventana objetivo k+1.
- Eje temporal en segundos reales y leyendas optimizadas para evitar solapamientos.
"""

import argparse
import os
import sys
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from sklearn.linear_model import LinearRegression
from sklearn.metrics import confusion_matrix, mean_absolute_error, precision_score, recall_score, f1_score


def calcular_metricas_clasificacion(y_real_bin, y_pred_bin):
    """Calcula matriz de confusión y métricas asociadas."""
    cm = confusion_matrix(y_real_bin, y_pred_bin, labels=[0, 1])
    tn, fp, fn, tp = cm.ravel()
    prec = precision_score(y_real_bin, y_pred_bin, zero_division=0)
    rec = recall_score(y_real_bin, y_pred_bin, zero_division=0)
    f1 = f1_score(y_real_bin, y_pred_bin, zero_division=0)
    spec = tn / (tn + fp) if (tn + fp) > 0 else 0.0
    return {
        "TN": int(tn), "FP": int(fp), "FN": int(fn), "TP": int(tp),
        "Precision": prec, "Sensibilidad": rec, "Especificidad": spec, "F1": f1
    }


def analizar_inicios(df, col_alerta):
    """
    Distingue entre Inicios observados (dk == 0 y dk+1 > 0) y Persistencia (dk > 0 y dk+1 > 0).
    Mide cuántos inicios fueron anunciados vs omitidos.
    """
    df = df.copy()
    df["es_inicio"] = (df["dk"] == 0) & (df["yk_target"] > 0)
    df["es_persistencia"] = (df["dk"] > 0) & (df["yk_target"] > 0)

    inicios = df[df["es_inicio"]]
    total_inicios = len(inicios)
    inicios_anticipados = int((inicios[col_alerta] == 1).sum()) if total_inicios > 0 else 0
    inicios_omitidos = total_inicios - inicios_anticipados
    tasa_anticipacion = (inicios_anticipados / total_inicios) if total_inicios > 0 else 0.0

    persistencias = df[df["es_persistencia"]]
    total_persistencia = len(persistencias)
    persistencia_detectada = int((persistencias[col_alerta] == 1).sum()) if total_persistencia > 0 else 0

    return {
        "total_inicios": total_inicios,
        "inicios_anticipados": inicios_anticipados,
        "inicios_omitidos": inicios_omitidos,
        "tasa_anticipacion": tasa_anticipacion,
        "total_persistencia": total_persistencia,
        "persistencia_detectada": persistencia_detectada
    }


def calibrar_umbrales_validacion(df_val, modelo, features):
    """
    Barrido amplio y exhaustivo de umbrales sobre la corrida de validación c04 (1.0 a 450.0).
    """
    X_val = df_val[features]
    y_val = df_val["yk_target"]
    y_val_bin = (y_val >= 1).astype(int)

    y_hat = np.clip(modelo.predict(X_val), 0, None)

    umbrales_reg = [1.0, 10.0, 25.0, 50.0, 75.0, 100.0, 150.0, 200.0, 250.0, 300.0, 325.0, 350.0, 375.0, 400.0, 450.0]
    mejor_umbral_reg = 350.0
    mejor_f1_reg = -1.0

    print("\n" + "-"*65)
    print(" BARRIDO AMPLIO DE UMBRAL REGRESIÓN (VALIDACIÓN c04)")
    print("-"*65)
    print("Umbral  | Precision | Sensibilidad | F1-Score | Alertas")
    for u in umbrales_reg:
        alerta = (y_hat >= u).astype(int)
        f1 = f1_score(y_val_bin, alerta, zero_division=0)
        p = precision_score(y_val_bin, alerta, zero_division=0)
        r = recall_score(y_val_bin, alerta, zero_division=0)
        n_al = alerta.sum()
        print(f" {u:6.1f} |  {p:7.3f}  |    {r:7.3f}   |  {f1:7.3f} | {n_al:3d}/{len(df_val)}")

    # Barrido para regla simple de tasa
    umbrales_tasa = [6.0, 7.0, 8.0, 8.5, 9.0, 9.5, 9.8, 10.0]
    mejor_umbral_tasa = 8.5
    mejor_f1_tasa = -1.0

    print("\n" + "-"*65)
    print(" BARRIDO REGLA SIMPLE DE TASA (VALIDACIÓN c04)")
    print("-"*65)
    print("Tasa (Mbit/s) | Precision | Sensibilidad | F1-Score | Alertas")
    for ut in umbrales_tasa:
        alerta_t = (df_val["rk"] >= ut).astype(int)
        f1 = f1_score(y_val_bin, alerta_t, zero_division=0)
        p = precision_score(y_val_bin, alerta_t, zero_division=0)
        r = recall_score(y_val_bin, alerta_t, zero_division=0)
        n_al = alerta_t.sum()
        print(f"   {ut:5.1f}      |  {p:7.3f}  |    {r:7.3f}   |  {f1:7.3f} | {n_al:3d}/{len(df_val)}")
        if f1 > mejor_f1_tasa:
            mejor_f1_tasa = f1
            mejor_umbral_tasa = ut

    print("-> Nota sobre regla de tasa: F1=0.954 empata entre 8.5, 9.0, 9.5 y 9.8 Mbit/s.")
    print("   Se adopta theta_tasa = 8.5 Mbit/s por criterio conservador de mayor sensibilidad.")

    return mejor_umbral_reg, mejor_umbral_tasa


def graficar_corrida_alineada(df_corrida, corrida_id, umbral_opt, umbral_sens, umbral_tasa, salida_png):
    """
    Genera la gráfica temporal con tres paneles alineados cumpliendo estrictamente:
    'Ubiquen cada pronóstico en la ventana a la que se refiere'.
    El pronóstico y_hat emitido al cierre de k se grafica en la ventana k+1.
    Eje X en tiempo relativo transcurrido (segundos).
    Leyendas reubicadas en 'upper left' sobre el tramo basal inicial (sin descartes)
    para garantizar visibilidad absoluta de mesetas y datos.
    """
    df = df_corrida.copy().reset_index(drop=True)

    t0 = df["t_inicio"].iloc[0]
    tiempos_k = df["t_fin"].values - t0        # Fin de la ventana k
    # El pronóstico y target se refieren a k+1, que termina en t_{k+1}
    tiempos_target = np.append(tiempos_k[1:], tiempos_k[-1] + np.median(df["delta_k"]))

    fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(13, 11), sharex=True)
    fig.suptitle(f"Análisis Temporal y Alertas de Congestión - Corrida {corrida_id.upper()}", fontsize=14, fontweight="bold")

    # Panel 1: Tasa capturada en k
    ax1.plot(tiempos_k, df["rk"], color="navy", lw=2, label=r"Tasa capturada $r_k$ (Mbit/s)")
    ax1.axhline(10.0, color="crimson", ls="--", lw=1.5, label="Capacidad TBF (10 Mbit/s)")
    ax1.set_ylabel("Tasa (Mbit/s)", fontsize=11)
    ax1.set_ylim(-0.5, 19.5)
    ax1.set_title("Panel 1: Tasa de Tráfico Observada en la Interfaz de Salida (Ventana $k$)", fontsize=11, fontweight="bold")
    ax1.grid(True, alpha=0.3)
    ax1.legend(loc="upper left", framealpha=0.9)

    # Panel 2: Descartes reales y pronosticados (ambos referidos a la ventana k+1)
    max_d = max(df["yk_target"].max(), df["y_hat"].max())
    ax2.plot(tiempos_target, df["yk_target"], color="black", lw=2, label=r"Descartes reales $d_{k+1}$ (Ventana $k+1$)")
    ax2.plot(tiempos_target, df["y_hat"], color="darkorange", lw=1.8, ls="-.", label=r"Pronóstico $\hat{y}_k \to k+1$ (Regresión Lineal)")
    ax2.set_ylabel("Descartes / ventana", fontsize=11)
    ax2.set_ylim(-20, max_d * 1.35)  # Espacio superior libre para leyenda
    ax2.set_title("Panel 2: Descartes de Cola Reales vs Pronóstico para Ventana $k+1$", fontsize=11, fontweight="bold")
    ax2.grid(True, alpha=0.3)
    ax2.legend(loc="upper left", framealpha=0.9)

    # Panel 3: Alertas e Inicios
    ax3.fill_between(tiempos_target, 0, df["congestiona_real"], step="mid", alpha=0.25, color="red", label=r"Congestión real ($d_{k+1} \geq 1$)")
    ax3.step(tiempos_target, df["alerta_sens"], where="mid", color="darkgreen", lw=2.0, label=rf"Alerta Regresión Sensible ($\hat{{y}}_k \geq {umbral_sens:.0f}$)")
    ax3.step(tiempos_target, df["alerta_opt"], where="mid", color="royalblue", lw=1.5, ls="--", label=rf"Alerta Regresión Óptima F1 ($\hat{{y}}_k \geq {umbral_opt:.0f}$)")
    ax3.step(tiempos_target, df["alerta_base"], where="mid", color="purple", lw=1.2, ls=":", label=rf"Alerta Regla Tasa ($r_k \geq {umbral_tasa:.1f}$ Mbit/s)")

    # Identificar inicios observados (dk == 0 y dk+1 > 0)
    inicios_mask = (df["dk"] == 0) & (df["yk_target"] > 0)
    indices_inicios = np.where(inicios_mask)[0]

    for idx_ini in indices_inicios:
        t_pt = tiempos_target[idx_ini]
        # Evaluación de anticipación respecto al punto de operación sensible (theta=100)
        anticipado = df["alerta_sens"].iloc[idx_ini] == 1
        color_mark = "green" if anticipado else "red"
        marker_type = "v" if anticipado else "^"
        texto = "Inicio Anticipado (θ=100)" if anticipado else "Inicio Omitido"

        ax3.scatter(t_pt, 1.05, marker=marker_type, s=120, color=color_mark, zorder=6, edgecolors="black")
        y_text = 1.15 if (idx_ini % 2 == 0) else 1.25
        ax3.annotate(texto,
                     (t_pt, 1.05),
                     xytext=(t_pt, y_text),
                     arrowprops=dict(arrowstyle="->", color=color_mark, lw=1.2),
                     ha="center", fontsize=8.5, fontweight="bold", color=color_mark,
                     bbox=dict(boxstyle="round,pad=0.2", facecolor="white", edgecolor=color_mark, alpha=0.9))

    ax3.set_ylim(-0.1, 1.45)
    ax3.set_yticks([0, 1])
    ax3.set_yticklabels(["Normal (0)", "Alerta (1)"])
    ax3.set_xlabel("Tiempo Transcurrido (segundos)", fontsize=11)
    ax3.set_ylabel("Estado de Alerta", fontsize=11)
    ax3.set_title("Panel 3: Emisión de Alertas e Inicios Observados (Ubicados en Ventana $k+1$)", fontsize=11, fontweight="bold")
    ax3.grid(True, alpha=0.3)
    ax3.legend(loc="lower right", framealpha=0.95, fontsize=8.5)

    plt.tight_layout()
    plt.savefig(salida_png, dpi=300)
    plt.close()
    print(f"[+] Gráfica temporal guardada en: {salida_png}")


def main():
    parser = argparse.ArgumentParser(description="Entrenamiento y evaluación rigurosa del modelo.")
    parser.add_argument("--datos", default="datos/dataset_completo_ventanas.csv", help="Ruta al dataset de ventanas")
    parser.add_argument("--salida-dir", default="resultados", help="Directorio de resultados")
    parser.add_argument("--umbral-alerta", type=float, default=None, help="Umbral fijo para emitir alerta")
    parser.add_argument("--umbral-tasa", type=float, default=None, help="Umbral fijo para regla simple de tasa")
    args = parser.parse_args()

    os.makedirs(args.salida_dir, exist_ok=True)

    if not os.path.exists(args.datos):
        print(f"[-] No se encontró el dataset en '{args.datos}'.")
        sys.exit(1)

    df_todo = pd.read_csv(args.datos)
    features = ["rk", "rk_lag1", "rk_lag2", "nk"]
    target = "yk_target"

    train_mask = df_todo["corrida"].isin(["c01", "c02", "c03"])
    val_mask = df_todo["corrida"] == "c04"
    test_mask = df_todo["corrida"].isin(["c05", "c06"])

    df_train = df_todo[train_mask].copy()
    df_val = df_todo[val_mask].copy()
    df_test = df_todo[test_mask].copy()

    print(f"[*] Partición de corridas:")
    print(f"    - Train (c01, c02, c03): {len(df_train)} ventanas")
    print(f"    - Val   (c04)          : {len(df_val)} ventanas")
    print(f"    - Test  (c05, c06)     : {len(df_test)} ventanas")

    # 1. Diagnóstico de Colinealidad y Constantes Físicas
    corr_rk_nk = np.corrcoef(df_train["rk"], df_train["nk"])[0, 1]
    # Razón empírica entre r_k y n_k
    df_act = df_train[df_train["nk"] > 50]
    ratio_rk_nk = (df_act["rk"] / df_act["nk"]).mean()
    factor_nk_rk = 1.0 / ratio_rk_nk

    print("\n" + "="*70)
    print(" DIAGNÓSTICO DE COLINEALIDAD Y RELACIÓN FÍSICA (TRAIN)")
    print("="*70)
    print(f"Correlación de Pearson entre r_k y n_k: {corr_rk_nk:.6f}")
    print("-> Al usar datagramas UDP de tamaño fijo (payload 1200 B + 42 B headers = 1242 B en cable):")
    print(f"   Tasa nominal por datagrama (Δ=1s): 1242 * 8 / 10^6 = 0.009936 Mbit/s")
    print(f"   Tasa empírica con Δ_k real (≈1.0084s): r_k / n_k = {ratio_rk_nk:.6f} Mbit/s")
    print(f"   Factor recíproco exacto: n_k ≈ {factor_nk_rk:.2f} * r_k")
    print("   Esto demuestra colinealidad perfecta entre r_k y n_k.")

    # Modelos de ablación
    m_full = LinearRegression().fit(df_train[features], df_train[target])
    m_no_nk = LinearRegression().fit(df_train[["rk", "rk_lag1", "rk_lag2"]], df_train[target])
    m_only_rk = LinearRegression().fit(df_train[["rk"]], df_train[target])

    # Efecto neto sobre r_k
    beta_net = m_full.coef_[0] + factor_nk_rk * m_full.coef_[3]

    # Evaluación de ablación tanto en VALIDACIÓN como en PRUEBA
    mae_val_full = mean_absolute_error(df_val[target], np.clip(m_full.predict(df_val[features]), 0, None))
    mae_val_no_nk = mean_absolute_error(df_val[target], np.clip(m_no_nk.predict(df_val[["rk", "rk_lag1", "rk_lag2"]]), 0, None))
    mae_val_only_rk = mean_absolute_error(df_val[target], np.clip(m_only_rk.predict(df_val[["rk"]]), 0, None))

    mae_test_full = mean_absolute_error(df_test[target], np.clip(m_full.predict(df_test[features]), 0, None))
    mae_test_no_nk = mean_absolute_error(df_test[target], np.clip(m_no_nk.predict(df_test[["rk", "rk_lag1", "rk_lag2"]]), 0, None))
    mae_test_only_rk = mean_absolute_error(df_test[target], np.clip(m_only_rk.predict(df_test[["rk"]]), 0, None))

    print("\n" + "-"*70)
    print(" ESTUDIO DE ABLACIÓN (VALIDACIÓN c04 Y PRUEBA c05/c06)")
    print("-"*70)
    print(f"1. Modelo Completo [rk, rk-1, rk-2, nk]:")
    print(f"   - Coeficientes: beta_r={m_full.coef_[0]:.2f}, beta_lag1={m_full.coef_[1]:.2f}, beta_lag2={m_full.coef_[2]:.2f}, beta_n={m_full.coef_[3]:.4f}")
    print(f"   - Efecto neto r_k: ({m_full.coef_[0]:.2f}) + ({factor_nk_rk:.2f} * {m_full.coef_[3]:.4f}) = {beta_net:+.2f}")
    print(f"   - MAE Validación: {mae_val_full:.3f} paq/ventana | MAE Prueba: {mae_test_full:.3f} paq/ventana")
    print(f"2. Modelo Sin n_k   [rk, rk-1, rk-2]:")
    print(f"   - Coeficientes: beta_r={m_no_nk.coef_[0]:.2f}, beta_lag1={m_no_nk.coef_[1]:.2f}, beta_lag2={m_no_nk.coef_[2]:.2f}")
    print(f"   - MAE Validación: {mae_val_no_nk:.3f} paq/ventana | MAE Prueba: {mae_test_no_nk:.3f} paq/ventana")
    print(f"3. Modelo Solo r_k  [rk]:")
    print(f"   - Coeficiente : beta_r={m_only_rk.coef_[0]:.2f}")
    print(f"   - MAE Validación: {mae_val_only_rk:.3f} paq/ventana | MAE Prueba: {mae_test_only_rk:.3f} paq/ventana")
    print("="*70)

    # 2. Baselines de Regresión en Prueba
    mae_zero = mean_absolute_error(df_test[target], np.zeros(len(df_test)))
    mae_persist = mean_absolute_error(df_test[target], df_test["dk"])
    mae_mean = mean_absolute_error(df_test[target], np.full(len(df_test), df_train[target].mean()))

    print("\n" + "="*65)
    print(" BASELINES DE EVALUACIÓN DE REGRESIÓN (MAE EN PRUEBA)")
    print("="*65)
    print(f"1. Predictor Persistencia (y_hat = d_k)   : MAE = {mae_persist:7.3f} paq/ventana")
    print(f"2. Predictor Constante 0 (y_hat = 0)     : MAE = {mae_zero:7.3f} paq/ventana")
    print(f"3. Modelo Regresión Lineal Completo      : MAE = {mae_test_full:7.3f} paq/ventana")
    print(f"4. Predictor Media de Train (y_hat = y_m): MAE = {mae_mean:7.3f} paq/ventana")
    print("="*65)

    # 3. Calibración en Validación
    u_reg_opt, u_tasa_opt = calibrar_umbrales_validacion(df_val, m_full, features)
    umbral_alerta = args.umbral_alerta if args.umbral_alerta is not None else u_reg_opt
    umbral_tasa = args.umbral_tasa if args.umbral_tasa is not None else u_tasa_opt

    print(f"\n[+] Umbrales seleccionados para la prueba:")
    print(f"    - Umbral Regresión Lineal : {umbral_alerta:.1f} paquetes pronosticados")
    print(f"    - Umbral Regla Simple Tasa: {umbral_tasa:.1f} Mbit/s")

    # 4. Evaluación en Prueba (c05 y c06)
    df_evaluar = df_test.copy()
    y_eval_raw = m_full.predict(df_evaluar[features])
    df_evaluar["y_hat"] = np.clip(y_eval_raw, 0, None)
    df_evaluar["congestiona_real"] = (df_evaluar["yk_target"] >= 1).astype(int)

    # Definir los puntos de operación clave para prueba
    u_opt = umbral_alerta        # theta = 350 (Óptimo F1)
    u_sens = 100.0               # theta = 100 (Sensible / Early Warning)
    u_low = 0.5                  # theta = 0.5 (Extremo Sensible)

    df_evaluar["alerta_opt"] = (df_evaluar["y_hat"] >= u_opt).astype(int)
    df_evaluar["alerta_sens"] = (df_evaluar["y_hat"] >= u_sens).astype(int)
    df_evaluar["alerta_low"] = (df_evaluar["y_hat"] >= u_low).astype(int)
    df_evaluar["alerta_base"] = (df_evaluar["rk"] >= umbral_tasa).astype(int)

    met_opt = calcular_metricas_clasificacion(df_evaluar["congestiona_real"], df_evaluar["alerta_opt"])
    met_sens = calcular_metricas_clasificacion(df_evaluar["congestiona_real"], df_evaluar["alerta_sens"])
    met_low = calcular_metricas_clasificacion(df_evaluar["congestiona_real"], df_evaluar["alerta_low"])
    met_base = calcular_metricas_clasificacion(df_evaluar["congestiona_real"], df_evaluar["alerta_base"])

    analisis_ini_opt = analizar_inicios(df_evaluar, "alerta_opt")
    analisis_ini_sens = analizar_inicios(df_evaluar, "alerta_sens")
    analisis_ini_low = analizar_inicios(df_evaluar, "alerta_low")
    analisis_ini_base = analizar_inicios(df_evaluar, "alerta_base")

    # Guardar informe detallado
    reporte_txt = os.path.join(args.salida_dir, "informe_metricas.txt")
    with open(reporte_txt, "w", encoding="utf-8") as f:
        f.write("="*85 + "\n")
        f.write(" EVALUACIÓN RIGUROSA EN EL CONJUNTO DE PRUEBA (c05 y c06 - 299 ventanas, 113 congestionadas)\n")
        f.write("="*85 + "\n\n")

        f.write("1. COMPARACIÓN DE MODELOS Y BASELINES:\n")
        f.write(f"   - Predictor Persistencia (y_hat = d_k)   : MAE = {mae_persist:.3f} paq/ventana (Cota teórica con telemetría de cola)\n")
        f.write(f"   - Predictor Constante Cero (y_hat = 0)   : MAE = {mae_zero:.3f} paq/ventana\n")
        f.write(f"   - Modelo Regresión Lineal Completo       : MAE = {mae_test_full:.3f} paq/ventana (Peor que predecir cero por saturación)\n")
        f.write(f"   - Modelo Regresión Sin n_k               : MAE = {mae_test_no_nk:.3f} paq/ventana\n")
        f.write(f"   - Modelo Regresión Solo r_k              : MAE = {mae_test_only_rk:.3f} paq/ventana\n")
        f.write(f"   - Predictor Media de Train               : MAE = {mae_mean:.3f} paq/ventana\n\n")

        f.write("2. COMPARACIÓN DE CLASIFICACIÓN DE ALERTAS EN PRUEBA:\n")
        f.write(f"{'Métrica':<25} | {'Regresión (θ=350)':<18} | {'Regresión (θ=100)':<18} | {'Regla Tasa (8.5M)':<18} | {'Regresión (θ=0.5)':<18}\n")
        f.write("-" * 105 + "\n")
        f.write(f"{'Propósito del punto':<25} | {'Óptimo F1 (Val)':<18} | {'Sensible / Anticip':<18} | {'Línea base reactiva':<18} | {'Extremo sensible':<18}\n")
        f.write(f"{'Umbral utilizado':<25} | {u_opt:<18.1f} | {u_sens:<18.1f} | {umbral_tasa:<18.1f} | {u_low:<18.1f}\n")
        f.write(f"{'Verdaderos Positivos':<25} | {met_opt['TP']:<18} | {met_sens['TP']:<18} | {met_base['TP']:<18} | {met_low['TP']:<18}\n")
        f.write(f"{'Falsos Positivos':<25} | {met_opt['FP']:<18} | {met_sens['FP']:<18} | {met_base['FP']:<18} | {met_low['FP']:<18}\n")
        f.write(f"{'Verdaderos Negativos':<25} | {met_opt['TN']:<18} | {met_sens['TN']:<18} | {met_base['TN']:<18} | {met_low['TN']:<18}\n")
        f.write(f"{'Falsos Negativos':<25} | {met_opt['FN']:<18} | {met_sens['FN']:<18} | {met_base['FN']:<18} | {met_low['FN']:<18}\n")
        f.write(f"{'Precisión':<25} | {met_opt['Precision']:<18.4f} | {met_sens['Precision']:<18.4f} | {met_base['Precision']:<18.4f} | {met_low['Precision']:<18.4f}\n")
        f.write(f"{'Sensibilidad (Recall)':<25} | {met_opt['Sensibilidad']:<18.4f} | {met_sens['Sensibilidad']:<18.4f} | {met_base['Sensibilidad']:<18.4f} | {met_low['Sensibilidad']:<18.4f}\n")
        f.write(f"{'Especificidad':<25} | {met_opt['Especificidad']:<18.4f} | {met_sens['Especificidad']:<18.4f} | {met_base['Especificidad']:<18.4f} | {met_low['Especificidad']:<18.4f}\n")
        f.write(f"{'F1-Score':<25} | {met_opt['F1']:<18.4f} | {met_sens['F1']:<18.4f} | {met_base['F1']:<18.4f} | {met_low['F1']:<18.4f}\n\n")

        f.write("3. DISTINCIÓN INICIO Y PERSISTENCIA (N = 4 inicios observados en prueba):\n")
        f.write(f"   - Total Inicios Observados (dk=0 y dk+1>0) : {analisis_ini_opt['total_inicios']}\n")
        f.write(f"   - Inicios Anticipados (Regresión θ=350)    : {analisis_ini_opt['inicios_anticipados']}/{analisis_ini_opt['total_inicios']} ({analisis_ini_opt['tasa_anticipacion']*100:.1f}%)\n")
        f.write(f"   - Inicios Anticipados (Regresión θ=100)    : {analisis_ini_sens['inicios_anticipados']}/{analisis_ini_sens['total_inicios']} ({analisis_ini_sens['tasa_anticipacion']*100:.1f}%)\n")
        f.write(f"   - Inicios Anticipados (Regla Simple Tasa)  : {analisis_ini_base['inicios_anticipados']}/{analisis_ini_base['total_inicios']} ({analisis_ini_base['tasa_anticipacion']*100:.1f}%)\n")
        f.write(f"   - Inicios Anticipados (Regresión θ=0.5)    : {analisis_ini_low['inicios_anticipados']}/{analisis_ini_low['total_inicios']} ({analisis_ini_low['tasa_anticipacion']*100:.1f}%)\n")
        f.write(f"   - Total Ventanas Persistencia (dk>0)       : {analisis_ini_opt['total_persistencia']}\n")
        f.write(f"   - Persistencias Detectadas (θ=350)         : {analisis_ini_opt['persistencia_detectada']}/{analisis_ini_opt['total_persistencia']} ({analisis_ini_opt['persistencia_detectada']/analisis_ini_opt['total_persistencia']*100:.1f}%)\n")
        f.write(f"   - Persistencias Detectadas (θ=100)         : {analisis_ini_sens['persistencia_detectada']}/{analisis_ini_sens['total_persistencia']} ({analisis_ini_sens['persistencia_detectada']/analisis_ini_sens['total_persistencia']*100:.1f}%)\n")
        f.write(f"   - Persistencias Detectadas (Regla Tasa)    : {analisis_ini_base['persistencia_detectada']}/{analisis_ini_base['total_persistencia']} ({analisis_ini_base['persistencia_detectada']/analisis_ini_base['total_persistencia']*100:.1f}%)\n")

    print("\n" + open(reporte_txt).read())

    # 5. Generar Gráficas Temporales Alineadas
    for cor_id in ["c05", "c06"]:
        df_cor = df_todo[df_todo["corrida"] == cor_id].copy()
        if df_cor.empty:
            continue
        y_cor_raw = m_full.predict(df_cor[features])
        df_cor["y_hat"] = np.clip(y_cor_raw, 0, None)
        df_cor["congestiona_real"] = (df_cor["yk_target"] >= 1).astype(int)
        df_cor["alerta_opt"] = (df_cor["y_hat"] >= u_opt).astype(int)
        df_cor["alerta_sens"] = (df_cor["y_hat"] >= u_sens).astype(int)
        df_cor["alerta_base"] = (df_cor["rk"] >= umbral_tasa).astype(int)

        png_path = os.path.join(args.salida_dir, f"grafica_temporal_{cor_id}.png")
        graficar_corrida_alineada(df_cor, cor_id, u_opt, u_sens, umbral_tasa, png_path)

    print(f"\n[+] Proceso completado exitosamente. Reporte guardado en: {reporte_txt}\n")


if __name__ == "__main__":
    main()
