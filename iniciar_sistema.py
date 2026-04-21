"""
iniciar_sistema.py
Lanzador principal del sistema EPIPROCESS
Inicia todos los servicios del backend en paralelo:
  1. Servidor Dashboard (puerto 8000)
  2. Monitor Google Drive via Apps Script bridge (bridge_drive.js)
  3. Procesamiento de archivos locales pendientes

Uso:
  python iniciar_sistema.py                → Inicia todo (dashboard + monitoreo + procesa locales)
  python iniciar_sistema.py --solo-dash    → Solo inicia el dashboard
  python iniciar_sistema.py --solo-bridge  → Solo inicia el bridge/monitoreo
  python iniciar_sistema.py --solo-local   → Solo procesa archivos locales
  python iniciar_sistema.py --intervalo 60 → Cambia intervalo de monitoreo a 60s
"""

import sys
import os
import time
import signal
import subprocess
import threading
from pathlib import Path
from datetime import datetime

# Agregar proyecto al path
BASE_DIR = Path(__file__).parent
sys.path.insert(0, str(BASE_DIR))

from config.settings import Settings
from scripts.utils import Logger


# ============================================================
# CONFIGURACIÓN
# ============================================================

PYTHON_EXE = sys.executable
NODE_EXE = "node"
SERVIDOR_DASHBOARD = str(BASE_DIR / "servidor_dashboard.py")
BRIDGE_DRIVE = str(BASE_DIR / "bridge_drive.js")
MAIN_PY = str(BASE_DIR / "main.py")

# Colores para la terminal
VERDE = "\033[92m"
AZUL = "\033[94m"
AMARILLO = "\033[93m"
ROJO = "\033[91m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"
DIM = "\033[2m"


class SistemaEPIPROCESS:
    """
    Orquestador principal que levanta todos los servicios del backend EPIPROCESS
    """

    def __init__(self, intervalo_bridge: int = 30):
        self.logger = Logger()
        self.settings = Settings()
        self.procesos = []
        self.hilos = []
        self.ejecutando = True
        self.intervalo_bridge = intervalo_bridge

        # Registrar señal de parada limpia
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, sig, frame):
        """Manejo limpio de Ctrl+C"""
        print(f"\n\n{AMARILLO}⏹  Deteniendo todos los servicios...{RESET}")
        self.ejecutando = False
        self._detener_procesos()

    def _detener_procesos(self):
        """Detiene todos los subprocesos activos"""
        for proc in self.procesos:
            try:
                if proc.poll() is None:
                    proc.terminate()
                    proc.wait(timeout=5)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
        self.procesos.clear()

    # ============================================================
    # SERVICIO 1: Dashboard HTTP (puerto 8000)
    # ============================================================

    def iniciar_dashboard(self):
        """Inicia el servidor del dashboard en un subproceso"""
        self.logger.info("Iniciando servidor Dashboard...")
        print(f"\n{AZUL}{'─'*60}")
        print(f"  🖥️  DASHBOARD — Servidor HTTP")
        print(f"{'─'*60}{RESET}")
        print(f"  Puerto:    {CYAN}http://localhost:8000{RESET}")
        print(f"  Archivo:   servidor_dashboard.py")
        print(f"  Estado:    Iniciando...\n")

        try:
            proc = subprocess.Popen(
                [PYTHON_EXE, SERVIDOR_DASHBOARD],
                cwd=str(BASE_DIR),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                encoding="utf-8",
                errors="replace"
            )
            self.procesos.append(proc)

            # Hilo para leer la salida del dashboard
            hilo = threading.Thread(
                target=self._leer_salida,
                args=(proc, "DASHBOARD"),
                daemon=True
            )
            hilo.start()
            self.hilos.append(hilo)

            print(f"  {VERDE}✓ Dashboard iniciado (PID: {proc.pid}){RESET}\n")
            return True

        except FileNotFoundError:
            print(f"  {ROJO}✗ No se encontró servidor_dashboard.py{RESET}\n")
            return False
        except Exception as e:
            print(f"  {ROJO}✗ Error iniciando dashboard: {e}{RESET}\n")
            return False

    # ============================================================
    # SERVICIO 2: Bridge Google Drive (bridge_drive.js)
    # ============================================================

    def iniciar_bridge_monitoreo(self):
        """
        Ejecuta el bridge de Google Apps Script en ciclos periódicos.
        Descarga archivos nuevos y los procesa con main.py
        """
        self.logger.info("Iniciando monitoreo via bridge Apps Script...")
        print(f"\n{CYAN}{'─'*60}")
        print(f"  📡 BRIDGE — Monitoreo Google Drive (Apps Script)")
        print(f"{'─'*60}{RESET}")
        print(f"  Intervalo: {self.intervalo_bridge}s")
        print(f"  Archivo:   bridge_drive.js --procesar")
        print(f"  Estado:    Iniciando...\n")

        hilo = threading.Thread(
            target=self._ciclo_bridge,
            daemon=True
        )
        hilo.start()
        self.hilos.append(hilo)

        print(f"  {VERDE}✓ Monitoreo bridge activado{RESET}\n")
        return True

    def _ciclo_bridge(self):
        """Ciclo continuo que ejecuta bridge_drive.js --procesar cada N segundos"""
        ciclo = 0
        while self.ejecutando:
            ciclo += 1
            timestamp = datetime.now().strftime("%H:%M:%S")

            try:
                print(f"\n{DIM}[{timestamp}] Bridge ciclo #{ciclo} — Revisando Drive...{RESET}")

                resultado = subprocess.run(
                    [NODE_EXE, BRIDGE_DRIVE, "--procesar"],
                    cwd=str(BASE_DIR),
                    capture_output=True,
                    text=True,
                    timeout=120,
                    encoding="utf-8",
                    errors="replace"
                )

                # Mostrar salida relevante (filtrar líneas vacías)
                salida = resultado.stdout.strip()
                if salida:
                    for linea in salida.split("\n"):
                        linea = linea.strip()
                        if linea and not linea.startswith("=") and not linea.startswith("─"):
                            if "error" in linea.lower():
                                print(f"  {ROJO}{linea}{RESET}")
                            elif "✓" in linea or "OK" in linea or "✅" in linea:
                                print(f"  {VERDE}{linea}{RESET}")
                            elif "Ya procesado" in linea or "⊘" in linea:
                                print(f"  {DIM}{linea}{RESET}")
                            else:
                                print(f"  {linea}")

                if resultado.stderr:
                    for linea in resultado.stderr.strip().split("\n"):
                        if linea.strip():
                            print(f"  {ROJO}[BRIDGE ERR] {linea.strip()}{RESET}")

            except subprocess.TimeoutExpired:
                print(f"  {AMARILLO}⚠ Bridge timeout (>120s), reintentando...{RESET}")
            except FileNotFoundError:
                print(f"  {ROJO}✗ Node.js no encontrado. Instalar desde https://nodejs.org{RESET}")
                print(f"  {AMARILLO}  El monitoreo bridge no puede funcionar sin Node.js{RESET}")
                return
            except Exception as e:
                print(f"  {ROJO}[BRIDGE] Error: {e}{RESET}")

            # Esperar intervalo (en bloques de 1s para responder rápido a Ctrl+C)
            for _ in range(self.intervalo_bridge):
                if not self.ejecutando:
                    return
                time.sleep(1)

    # ============================================================
    # SERVICIO 3: Procesamiento de archivos locales
    # ============================================================

    def procesar_archivos_locales(self):
        """Procesa archivos que ya estén en la carpeta de entrada"""
        self.logger.info("Verificando archivos locales pendientes...")
        print(f"\n{VERDE}{'─'*60}")
        print(f"  📂 LOCAL — Procesamiento de archivos pendientes")
        print(f"{'─'*60}{RESET}")
        print(f"  Carpeta:   {self.settings.INPUT_DIR}")

        # Verificar si hay archivos pendientes
        archivos = list(self.settings.INPUT_DIR.glob("*"))
        archivos = [
            a for a in archivos
            if a.is_file() and a.suffix.lower() in [".xlsx", ".xls", ".csv", ".ods", ".xlsm"]
        ]

        if not archivos:
            print(f"  Estado:    {DIM}No hay archivos pendientes{RESET}\n")
            return True

        print(f"  Archivos:  {len(archivos)} pendiente(s)")
        print(f"  Estado:    Procesando...\n")

        try:
            resultado = subprocess.run(
                [PYTHON_EXE, MAIN_PY, "--local", "--boletin"],
                cwd=str(BASE_DIR),
                capture_output=True,
                text=True,
                timeout=600,
                encoding="utf-8",
                errors="replace"
            )

            if resultado.stdout:
                for linea in resultado.stdout.strip().split("\n"):
                    if linea.strip():
                        print(f"  {linea.strip()}")

            if resultado.returncode == 0:
                print(f"\n  {VERDE}✓ Procesamiento local completado{RESET}\n")
            else:
                print(f"\n  {AMARILLO}⚠ Procesamiento completado con advertencias{RESET}\n")
                if resultado.stderr:
                    for linea in resultado.stderr.strip().split("\n")[-5:]:
                        if linea.strip():
                            print(f"  {DIM}{linea.strip()}{RESET}")

            return True

        except subprocess.TimeoutExpired:
            print(f"  {ROJO}✗ Timeout procesando archivos locales{RESET}\n")
            return False
        except Exception as e:
            print(f"  {ROJO}✗ Error: {e}{RESET}\n")
            return False

    # ============================================================
    # LEER SALIDA DE SUBPROCESOS
    # ============================================================

    def _leer_salida(self, proc, nombre):
        """Lee la salida de un subproceso y la imprime"""
        try:
            for linea in iter(proc.stdout.readline, ''):
                if not self.ejecutando:
                    break
                linea = linea.strip()
                if linea:
                    # Filtrar líneas repetitivas del servidor HTTP
                    if "GET /" in linea or "POST /" in linea:
                        continue  # No mostrar cada request HTTP
                    print(f"  {DIM}[{nombre}] {linea}{RESET}")
        except Exception:
            pass

    # ============================================================
    # INICIO PRINCIPAL
    # ============================================================

    def iniciar_todo(self):
        """Inicia todos los servicios del sistema"""
        self._mostrar_banner()

        # 1. Procesar archivos locales pendientes primero
        self.procesar_archivos_locales()

        # 2. Iniciar dashboard
        self.iniciar_dashboard()

        # 3. Iniciar monitoreo bridge
        self.iniciar_bridge_monitoreo()

        # 4. Mantener vivo el proceso principal
        self._mantener_vivo()

    def _mostrar_banner(self):
        """Muestra el banner de inicio"""
        print(f"""
{BOLD}{VERDE}╔══════════════════════════════════════════════════════════════╗
║                                                              ║
║   ███████╗██████╗ ██╗██████╗ ██████╗  ██████╗  ██████╗       ║
║   ██╔════╝██╔══██╗██║██╔══██╗██╔══██╗██╔═══██╗██╔════╝       ║
║   █████╗  ██████╔╝██║██████╔╝██████╔╝██║   ██║██║            ║
║   ██╔══╝  ██╔═══╝ ██║██╔═══╝ ██╔══██╗██║   ██║██║            ║
║   ███████╗██║     ██║██║     ██║  ██║╚██████╔╝╚██████╗       ║
║   ╚══════╝╚═╝     ╚═╝╚═╝     ╚═╝  ╚═╝ ╚═════╝  ╚═════╝       ║
║                                                              ║
║   EPIPROCESS — Procesamiento Epidemiológico                  ║
║   Evento 549: Morbilidad Materna Extrema                    ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝{RESET}

{BOLD}📊 Configuración del sistema:{RESET}
  • Modo:              {CYAN}{self.settings.APP_MODE}{RESET}
  • Entrada:           {self.settings.INPUT_DIR}
  • Salida:            {self.settings.OUTPUT_DIR}
  • Boletines:         {"✓ Activado" if self.settings.ENABLE_BOLETIN else "✗ Desactivado"}
  • Filtro Risaralda:  {"✓ Solo dept. 66" if self.settings.FILTER_ONLY_RISARALDA else "✗ Todos los departamentos"}
  • Bridge intervalo:  {self.intervalo_bridge}s
  • Dashboard:         {CYAN}http://localhost:8000{RESET}

{BOLD}Servicios a iniciar:{RESET}
  1. 📂 Procesamiento de archivos locales pendientes
  2. 🖥️  Dashboard web (puerto 8000)
  3. 📡 Monitoreo continuo de Google Drive (bridge Apps Script)

  Presiona {BOLD}Ctrl+C{RESET} para detener todos los servicios
""")

    def _mantener_vivo(self):
        """Mantiene el proceso principal vivo mientras los servicios corren"""
        print(f"\n{VERDE}{'═'*60}")
        print(f"  ✓ SISTEMA EPIPROCESS INICIADO CORRECTAMENTE")
        print(f"{'═'*60}{RESET}")
        print(f"\n{DIM}  Esperando eventos... (Ctrl+C para detener){RESET}\n")

        try:
            while self.ejecutando:
                # Verificar que el dashboard siga vivo
                for proc in self.procesos:
                    if proc.poll() is not None:
                        print(f"\n{AMARILLO}⚠ Un servicio se detuvo inesperadamente{RESET}")
                        self.procesos.remove(proc)

                time.sleep(2)

        except KeyboardInterrupt:
            pass
        finally:
            self._detener_procesos()
            print(f"\n{BOLD}📊 Resumen de sesión:{RESET}")
            print(f"  • Finalizado: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"\n{VERDE}✓ Sistema EPIPROCESS detenido correctamente{RESET}\n")


# ============================================================
# PUNTO DE ENTRADA
# ============================================================

def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="EPIPROCESS — Sistema de procesamiento epidemiológico",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  python iniciar_sistema.py                → Todo: dashboard + monitoreo + procesa locales
  python iniciar_sistema.py --solo-dash    → Solo dashboard web
  python iniciar_sistema.py --solo-bridge  → Solo monitoreo Drive (bridge)
  python iniciar_sistema.py --solo-local   → Solo procesa archivos locales
  python iniciar_sistema.py --intervalo 30 → Monitoreo cada 30 segundos
        """
    )

    parser.add_argument("--solo-dash", action="store_true", help="Solo iniciar dashboard")
    parser.add_argument("--solo-bridge", action="store_true", help="Solo monitoreo bridge")
    parser.add_argument("--solo-local", action="store_true", help="Solo procesar archivos locales")
    parser.add_argument("--intervalo", type=int, default=30, help="Intervalo de monitoreo en segundos (default: 30)")

    args = parser.parse_args()

    sistema = SistemaEPIPROCESS(intervalo_bridge=args.intervalo)

    if args.solo_dash:
        sistema._mostrar_banner()
        sistema.iniciar_dashboard()
        sistema._mantener_vivo()

    elif args.solo_bridge:
        sistema._mostrar_banner()
        sistema.iniciar_bridge_monitoreo()
        sistema._mantener_vivo()

    elif args.solo_local:
        sistema._mostrar_banner()
        sistema.procesar_archivos_locales()

    else:
        # Modo completo: todo junto
        sistema.iniciar_todo()


if __name__ == "__main__":
    main()
