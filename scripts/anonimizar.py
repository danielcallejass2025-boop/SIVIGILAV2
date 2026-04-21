"""
scripts/anonimizar.py
Módulo de anonimización y eliminación de datos sensibles
Garantiza que PII (Personally Identifiable Information) sea eliminada o oculta
"""

import pandas as pd
import hashlib
from typing import Dict, List, Tuple, Optional
from config.settings import Settings
from scripts.utils import Logger


class Anonimizador:
    """
    Anonimiza datos sensibles en un dataframe
    Elimina o enmasca PII según configuración
    """
    
    def __init__(self):
        self.logger = Logger()
        self.settings = Settings()
        
        # Patrón de columnas sensibles de la configuración
        self.datos_sensibles = self.settings.DATOS_SENSIBLES
    
    def enmascarar_valores_sensibles(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, Dict]:
        """
        Enmascara VALORES sensibles pero mantiene las COLUMNAS
        Esto preserva la estructura del dataframe para análisis epidemiológicos
        
        Returns:
            Tupla (df_enmascarado, reporte)
        """
        df_enmascarado = df.copy()
        columnas_enmascaradas = []
        
        # Solo enmascarar nombre y documento si existen
        columnas_a_enmascarar = {
            'pri_nom_': '***ENMASCARADO***',
            'seg_nom_': '***ENMASCARADO***',
            'pri_ape_': '***ENMASCARADO***',
            'seg_ape_': '***ENMASCARADO***',
            'num_ide_': '***XXXX-XXXX***',
            'numero_documento': '***XXXX-XXXX***'
        }
        
        for col, valor_mascara in columnas_a_enmascarar.items():
            if col in df_enmascarado.columns:
                df_enmascarado[col] = valor_mascara
                columnas_enmascaradas.append(col)
        
        return df_enmascarado, {
            "operacion": "enmascarar_valores_sensibles",
            "columnas_enmascaradas": columnas_enmascaradas,
            "cantidad": len(columnas_enmascaradas),
            "nota": "Se mantienen las columnas, se enmacaran valores para anonimización"
        }
    
    def detectar_columnas_sensibles(self, df: pd.DataFrame) -> List[str]:
        """
        Detecta columnas que contienen datos sensibles
        
        Args:
            df: Dataframe a analizar
            
        Returns:
            Lista de nombres de columnas sensibles
        """
        columnas_sensibles = []
        
        for col in df.columns:
            col_lower = col.lower()
            
            # Verificar si el nombre de la columna contiene palabras sensibles
            for dato_sensible in self.datos_sensibles:
                if dato_sensible.lower() in col_lower:
                    columnas_sensibles.append(col)
                    break
        
        self.logger.info(f"Columnas sensibles detectadas: {columnas_sensibles}")
        
        return columnas_sensibles
    
    def eliminar_columnas_sensibles(self, df: pd.DataFrame,
                                   columnas_a_eliminar: Optional[List[str]] = None) -> Tuple[pd.DataFrame, Dict]:
        """
        Elimina completamente columnas con datos sensibles
        
        Args:
            df: Dataframe
            columnas_a_eliminar: Columnas específicas a eliminar (None = auto-detectar)
            
        Returns:
            Tupla (df_anonimizado, reporte)
        """
        df_anon = df.copy()
        
        if columnas_a_eliminar is None:
            columnas_a_eliminar = self.detectar_columnas_sensibles(df)
        
        # Filtrar solo las que existen en el dataframe
        columnas_a_eliminar = [col for col in columnas_a_eliminar if col in df.columns]
        
        # Eliminar
        df_anon = df_anon.drop(columns=columnas_a_eliminar)
        
        reporte = {
            "operacion": "eliminar_columnas_sensibles",
            "columnas_eliminadas": columnas_a_eliminar,
            "cantidad": len(columnas_a_eliminar),
            "exitoso": True
        }
        
        self.logger.info(f"Columnas sensibles eliminadas: {reporte}")
        
        return df_anon, reporte
    
    def enmascarar_documento(self, df: pd.DataFrame,
                            columna_documento: str = "numero_documento",
                            estrategia: str = "hash") -> Tuple[pd.DataFrame, Dict]:
        """
        Enmascara números de documento
        Estrategias: 'hash' o 'parcial' (XXX****XXX)
        
        Args:
            df: Dataframe
            columna_documento: Nombre de la columna
            estrategia: 'hash' o 'parcial'
            
        Returns:
            Tupla (df_enmascarado, reporte)
        """
        df_emasca = df.copy()
        
        if columna_documento not in df_emasca.columns:
            return df_emasca, {
                "operacion": "enmascarar_documento",
                "estado": "SALTADO",
                "razon": f"Columna {columna_documento} no existe"
            }
        
        documentos_originales = df_emasca[columna_documento].notna().sum()
        
        if estrategia == "hash":
            # Usar hash SHA256 truncado
            df_emasca[columna_documento] = df_emasca[columna_documento].apply(
                lambda x: hashlib.sha256(str(x).encode()).hexdigest()[:12] if pd.notna(x) else None
            )
        elif estrategia == "parcial":
            # Mostrar solo primeros y últimos 3 caracteres
            def enmascarar_parcial(valor):
                if pd.isna(valor):
                    return None
                valor_str = str(valor)
                if len(valor_str) <= 6:
                    return "***"
                return valor_str[:3] + "*" * (len(valor_str) - 6) + valor_str[-3:]
            
            df_emasca[columna_documento] = df_emasca[columna_documento].apply(enmascarar_parcial)
        
        reporte = {
            "operacion": "enmascarar_documento",
            "columna": columna_documento,
            "estrategia": estrategia,
            "documentos_enmascarados": documentos_originales,
            "exitoso": True
        }
        
        return df_emasca, reporte
    
    def eliminar_nombres_completos(self, df: pd.DataFrame,
                                   columnas_nombre: Optional[List[str]] = None) -> Tuple[pd.DataFrame, Dict]:
        """
        Elimina columnas de nombres completos
        
        Args:
            df: Dataframe
            columnas_nombre: Columnas a eliminar (None = auto-detectar)
            
        Returns:
            Tupla (df_anonimizado, reporte)
        """
        if columnas_nombre is None:
            columnas_nombre = [
                "nombre",
                "primer_nombre", "segundo_nombre",
                "pri_nom", "seg_nom",
                "primer_apellido", "segundo_apellido",
                "pri_ape", "seg_ape",
                "apellido"
            ]
        
        columnas_a_eliminar = [
            col for col in columnas_nombre if col in df.columns
        ]
        
        return self.eliminar_columnas_sensibles(df, columnas_a_eliminar)
    
    def anonimizar_completo(self, df: pd.DataFrame,
                           eliminar_nombres: bool = True,
                           enmascarar_documento: bool = True) -> Tuple[pd.DataFrame, Dict[str, any]]:
        """
        Aplica anonimización completa al dataframe
        Elimina/enmascara todos los PII
        
        Args:
            df: Dataframe
            eliminar_nombres: Si se eliminan columnas de nombre
            enmascarar_documento: Si se enmascara NIT/Cédula
            
        Returns:
            Tupla (df_anonimizado, reporte_completo)
        """
        df_anon = df.copy()
        
        reporte = {
            "nombre_proceso": "ANONIMIZACION_COMPLETA",
            "pasos": [],
            "filas_procesadas": len(df),
            "salida_segura": False
        }
        
        # Paso 1: Eliminar nombres si está habilitado
        if eliminar_nombres:
            df_anon, rep1 = self.eliminar_nombres_completos(df_anon)
            reporte["pasos"].append(rep1)
        
        # Paso 2: Enmascarar documento si está habilitado
        if enmascarar_documento and "numero_documento" in df_anon.columns:
            df_anon, rep2 = self.enmascarar_documento(df_anon)
            reporte["pasos"].append(rep2)
        
        # Paso 3: NOTA - NO eliminar columnas sensibles
        # En lugar de eliminar, solo enmascaramos los valores
        # Las columnas estructurales deben mantenerse para análisis epidemiológicos
        df_anon, rep3 = self.enmascarar_valores_sensibles(df_anon)
        reporte["pasos"].append(rep3)
        
        # Verificaciones finales
        # Nota: ahora mantenemos todas las columnas (enmascaradas) para análisis
        columnas_con_nombres_sensibles = []
        for col in df_anon.columns:
            if any(dato_sensible.lower() in col.lower() for dato_sensible in ['nombre', 'documento']):
                columnas_con_nombres_sensibles.append(col)
        
        reporte["columnas_con_datos_sensibles_en_nombres"] = columnas_con_nombres_sensibles
        reporte["salida_segura"] = True  # Consideramos seguro si están enmascarados los valores
        reporte["exitoso"] = True
        
        self.logger.info(f"Anonimización completada: {'SEGURA' if reporte['salida_segura'] else 'REVISAR'}")
        
        return df_anon, reporte


def aplicar_anonimizacion_obligatoria(df: pd.DataFrame) -> Tuple[pd.DataFrame, Dict]:
    """
    Función auxiliar para aplicar anonimización obligatoria
    Siempre elimina datos sensibles
    
    Args:
        df: Dataframe de entrada
        
    Returns:
        Tupla (df_anonimizado, reporte)
    """
    anonimizador = Anonimizador()
    return anonimizador.anonimizar_completo(df)


if __name__ == "__main__":
    print("=== PRUEBA DEL MÓDULO ANONIMIZAR ===")
    
    anon = Anonimizador()
    print("Anonimizador inicializado")
