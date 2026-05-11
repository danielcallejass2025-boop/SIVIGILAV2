"""
iniciar_sistema.py
Lanzador principal del sistema EPIPROCESS
Inicia todos los servicios del backend en paralelo:
  1. Servidor Dashboard (puerto 8000)
    2. Monitor Google Drive nativo (monitor.py + OAuth)
    3. (Opcional) Procesamiento de archivos locales pendientes

Uso:
    python iniciar_sistema.py                → Inicia dashboard + monitoreo (SIN procesar locales)
  python iniciar_sistema.py --solo-dash    → Solo inicia el dashboard
    python iniciar_sistema.py --solo-monitor → Solo inicia el monitoreo continuo
  python iniciar_sistema.py --solo-local   → Solo procesa archivos locales
    python iniciar_sistema.py --con-local    → Modo completo + procesamiento local inicial
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

for stream_name in ("stdout", "stderr"):
    stream = getattr(sys, stream_name, None)
    reconfigure = getattr(stream, "reconfigure", None)
    if callable(reconfigure):
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

# Agregar proyecto al path
BASE_DIR = Path(__file__).parent
sys.path.insert(0, str(BASE_DIR))

from config.settings import Settings
from scripts.utils import Logger


# ============================================================
# CONFIGURACIÓN
# ============================================================

SERVIDOR_DASHBOARD = str(BASE_DIR / "servidor_dashboard.py")
MONITOR_PY = str(BASE_DIR / "monitor.py")
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

    def __init__(self, intervalo_monitor: int = 30, procesar_local_arranque: bool = False):
        self.logger = Logger()
        self.settings = Settings()
        self.procesos = []
        self.hilos = []
        self.ejecutando = True
        self.intervalo_monitor = intervalo_monitor
        self.procesar_local_arranque = procesar_local_arranque
        self.python_exe = self._resolver_python_executable()

        # Registrar señal de parada limpia
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    @staticmethod
    def _candidatos_python() -> list[str]:
        """Devuelve candidatos de intérprete Python priorizando venv local."""
        candidatos = []

        env_py = os.getenv("EPIPROC_PYTHON_EXE", "").strip()
        if env_py:
            candidatos.append(env_py)

        base = BASE_DIR
        rutas_locales = [
            base / ".venv" / "Scripts" / "python.exe",
            base / "venv" / "Scripts" / "python.exe",
            base / ".venv" / "bin" / "python",
            base / "venv" / "bin" / "python",
        ]
        candidatos.extend(str(r) for r in rutas_locales if r.exists())
        candidatos.append(sys.executable)

        # Elimina duplicados preservando orden.
        vistos = set()
        unicos = []
        for ruta in candidatos:
            key = os.path.abspath(str(ruta)).lower()
            if key in vistos:
                continue
            vistos.add(key)
            unicos.append(str(ruta))

        return unicos

    @staticmethod
    def _python_tiene_modulo(python_exe: str, modulo: str) -> bool:
        """Verifica si un intérprete Python tiene disponible un módulo."""
        try:
            codigo = f"import importlib.util,sys;sys.exit(0 if importlib.util.find_spec('{modulo}') else 1)"
            resultado = subprocess.run(
                [python_exe, "-c", codigo],
                capture_output=True,
                text=True,
                timeout=6,
            )
            return resultado.returncode == 0
        except Exception:
            return False

    def _resolver_python_executable(self) -> str:
        """Resuelve el intérprete para subprocesos, priorizando uno con Flask."""
        candidatos = self._candidatos_python()

        for py in candidatos:
            if self._python_tiene_modulo(py, "flask"):
                if os.path.abspath(py).lower() != os.path.abspath(sys.executable).lower():
                    self.logger.info(f"Usando intérprete alterno para servicios: {py}")
                return py

        fallback = sys.executable
        self.logger.warning(
            "No se encontró intérprete con Flask en venv local. "
            f"Se usará el Python actual: {fallback}"
        )
        return fallback

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
                [self.python_exe, SERVIDOR_DASHBOARD],
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
    # SERVICIO 2: Monitor Google Drive nativo (monitor.py)
    # ============================================================

    def iniciar_monitor_monitoreo(self):
        """
        Ejecuta el monitor nativo de Google Drive en un subproceso.
        Usa OAuth directo y elimina la dependencia del bridge Apps Script.
        """
        self.logger.info("Iniciando monitoreo nativo de Google Drive...")
        print(f"\n{CYAN}{'─'*60}")
        print(f"  📡 MONITOR — Google Drive nativo (OAuth)")
        print(f"{'─'*60}{RESET}")
        print(f"  Intervalo: {self.intervalo_monitor}s")
        print(f"  Archivo:   monitor.py --intervalo {self.intervalo_monitor}")
        print(f"  Estado:    Iniciando...\n")

        try:
            proc = subprocess.Popen(
                [self.python_exe, MONITOR_PY, "--intervalo", str(self.intervalo_monitor)],
                cwd=str(BASE_DIR),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                encoding="utf-8",
                errors="replace"
            )
            self.procesos.append(proc)

            hilo = threading.Thread(
                target=self._leer_salida,
                args=(proc, "MONITOR"),
                daemon=True
            )
            hilo.start()
            self.hilos.append(hilo)

            print(f"  {VERDE}✓ Monitoreo nativo activado (PID: {proc.pid}){RESET}\n")
            return True

        except FileNotFoundError:
            print(f"  {ROJO}✗ No se encontró monitor.py{RESET}\n")
            return False
        except Exception as e:
            print(f"  {ROJO}✗ Error iniciando monitor nativo: {e}{RESET}\n")
            return False

    def iniciar_bridge_monitoreo(self):
        """Alias legacy para mantener compatibilidad con comandos antiguos."""
        return self.iniciar_monitor_monitoreo()

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
                [self.python_exe, MAIN_PY, "--local", "--boletin"],
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

        # 1. (Opcional) Procesar archivos locales pendientes primero
        if self.procesar_local_arranque:
            self.procesar_archivos_locales()
        else:
            print(f"\n{DIM}  • Procesamiento local inicial: desactivado (solo Drive){RESET}\n")

        # 2. Iniciar dashboard
        self.iniciar_dashboard()

        # 3. Iniciar monitoreo nativo
        self.iniciar_monitor_monitoreo()

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
    • Python servicios:  {self.python_exe}
  • Entrada:           {self.settings.INPUT_DIR}
  • Salida:            {self.settings.OUTPUT_DIR}
  • Boletines:         {"✓ Activado" if self.settings.ENABLE_BOLETIN else "✗ Desactivado"}
    • Filtro Risaralda:  {"✓ Solo dept. 66" if self.settings.FILTER_ONLY_RISARALDA else "✗ Todos los departamentos"}
    • Monitor intervalo: {self.intervalo_monitor}s
  • Dashboard:         {CYAN}http://localhost:8000{RESET}
    • Local al inicio:   {"✓ Activado" if self.procesar_local_arranque else "✗ Desactivado"}

{BOLD}Servicios a iniciar:{RESET}
    1. 🖥️  Dashboard web (puerto 8000)
    2. 📡 Monitoreo continuo de Google Drive (OAuth nativo)
    3. 📂 Procesamiento local inicial ({"activado" if self.procesar_local_arranque else "desactivado"})

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
    python iniciar_sistema.py                → dashboard + monitoreo (sin locales)
  python iniciar_sistema.py --solo-dash    → Solo dashboard web
    python iniciar_sistema.py --solo-monitor → Solo monitoreo Drive nativo
  python iniciar_sistema.py --solo-local   → Solo procesa archivos locales
    python iniciar_sistema.py --con-local    → dashboard + monitoreo + procesa locales
  python iniciar_sistema.py --intervalo 30 → Monitoreo cada 30 segundos
        """
    )

    parser.add_argument("--solo-dash", action="store_true", help="Solo iniciar dashboard")
    parser.add_argument("--solo-monitor", action="store_true", help="Solo monitoreo nativo de Drive")
    parser.add_argument("--solo-bridge", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--solo-local", action="store_true", help="Solo procesar archivos locales")
    parser.add_argument("--con-local", action="store_true", help="Procesar pendientes locales al iniciar modo completo")
    parser.add_argument("--intervalo", type=int, default=30, help="Intervalo de monitoreo en segundos (default: 30)")

    args = parser.parse_args()

    sistema = SistemaEPIPROCESS(
        intervalo_monitor=args.intervalo,
        procesar_local_arranque=args.con_local,
    )

    if args.solo_dash:
        sistema._mostrar_banner()
        sistema.iniciar_dashboard()
        sistema._mantener_vivo()

    elif args.solo_monitor or args.solo_bridge:
        sistema._mostrar_banner()
        sistema.iniciar_monitor_monitoreo()
        sistema._mantener_vivo()

    elif args.solo_local:
        sistema._mostrar_banner()
        sistema.procesar_archivos_locales()

    else:
        # Modo completo: todo junto
        sistema.iniciar_todo()


if __name__ == "__main__":
    main()
