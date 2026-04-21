"""
scripts/normalizador_columnas.py
Módulo para normalización y selección de columnas relevantes
Estandariza nombres de columnas y selecciona las variables clave para procesamiento
"""

import pandas as pd
from typing import Dict, List, Tuple, Optional
from scripts.utils import Logger, DetectorColumnas


class NormalizadorColumnas:
    """
    Normaliza y selecciona columnas relevantes del dataframe
    Mapea columnas originales a nombres estandarizados para el procesamiento
    """
    
    def __init__(self):
        self.logger = Logger()
        self.detector = DetectorColumnas()
        
        # Columnas consideradas "clave" para procesamiento
        self.columnas_clave = [
            "codigo_evento",
            "fecha_notificacion",
            "departamento",
            "municipio",
            "numero_documento",
            "tipo_documento",
            "sexo",
            "edad",
            "edad_meses",
            "primer_nombre",
            "segundo_nombre",
            "primer_apellido",
            "segundo_apellido",
            "fecha_nacimiento",
            "institucion",
            "fecha_egreso"
        ]
    
    def mapear_columnas(self, df: pd.DataFrame) -> Dict[str, Optional[str]]:
        """
        Mapea las columnas del dataframe a nombres estandarizados
        
        Args:
            df: Dataframe a mapear
            
        Returns:
            Diccionario {nombre_estandar: columna_original_encontrada_o_none}
        """
        mapeo = {}
        columnas_df = df.columns.tolist()
        
        for col_clave in self.columnas_clave:
            col_detectada = self.detector.detectar_columna(col_clave, columnas_df, umbral=70)
            mapeo[col_clave] = col_detectada
        
        self.logger.info(f"Mapeo de columnas completado")
        
        return mapeo
    
    def estandarizar_dataframe(self, df: pd.DataFrame, mapeo: Dict[str, Optional[str]]) -> pd.DataFrame:
        """
        Crea un nuevo dataframe con columnas normalizadas
        MANTIENE TODAS las columnas originales + agrega las estandarizadas
        
        Args:
            df: Dataframe original
            mapeo: Diccionario de mapeo {nombre_std: columna_original}
            
        Returns:
            DataFrame con TODAS las columnas (originales + estandarizadas)
        """
        df_std = df.copy()
        
        # Crear diccionario de renombramiento (solo las que existen)
        renombre = {v: k for k, v in mapeo.items() if v is not None and v in df.columns}
        
        # Renombrar las columnas mapeadas (pero mantener todas las originales)
        # Esto agregará las nuevas columnas estandarizadas sin eliminar nada
        for col_original, col_nuevo in renombre.items():
            df_std[col_nuevo] = df_std[col_original]
        
        # IMPORTANTE: NO eliminar las demás columnas, solo mantener TODO
        self.logger.info(f"Dataframe estandarizado: {len(df_std.columns)} columnas (mantiene todas las originales + estandarizadas)")
        
        return df_std
    
    def detectar_columnas_faltantes(self, mapeo: Dict[str, Optional[str]]) -> List[str]:
        """
        Detecta columnas clave que no fueron encontradas
        
        Args:
            mapeo: Diccionario de mapeo
            
        Returns:
            Lista de columnas faltantes
        """
        faltantes = [k for k, v in mapeo.items() if v is None]
        
        if faltantes:
            self.logger.warning(f"Columnas no detectadas: {faltantes}")
        
        return faltantes
    
    def agrupar_por_departamento(self, df: pd.DataFrame, departamento_target: str = "RISARALDA",
                                 columna_depto: Optional[str] = "departamento") -> Tuple[pd.DataFrame, int]:
        """
        Filtra el dataframe para mantener solo un departamento
        
        Args:
            df: Dataframe
            departamento_target: Departamento a filtrar
            columna_depto: Nombre de la columna de departamento
            
        Returns:
            Tupla (df_filtrado, filas_eliminadas)
        """
        if columna_depto not in df.columns:
            self.logger.warning(f"Columna {columna_depto} no encontrada, no se filtra")
            return df, 0
        
        filas_antes = len(df)
        
        # Normalizar valores de departamento para comparación
        df_filtrado = df.copy()
        df_filtrado["_depto_norm"] = df_filtrado[columna_depto].str.upper().str.strip()
        
        # Filtrar
        mask = df_filtrado["_depto_norm"] == departamento_target.upper().strip()
        df_filtrado = df_filtrado[mask].drop(columns=["_depto_norm"])
        
        filas_eliminadas = filas_antes - len(df_filtrado)
        
        self.logger.info(f"Filtro de departamento: {filas_eliminadas} filas eliminadas")
        
        return df_filtrado, filas_eliminadas
    
    def estandarizar_sexo(self, df: pd.DataFrame, columna_sexo: str = "sexo") -> pd.DataFrame:
        """
        Estandariza valores de sexo a códigos (M, F, O)
        
        Args:
            df: Dataframe
            columna_sexo: Nombre de la columna de sexo
            
        Returns:
            Dataframe con sexo estandarizado
        """
        if columna_sexo not in df.columns:
            return df
        
        df_std = df.copy()
        
        # Mapeos posibles
        mapeo_sexo = {
            'masculino': 'M',
            'm': 'M',
            '1': 'M',
            'hombre': 'M',
            'male': 'M',
            'femenino': 'F',
            'f': 'F',
            '2': 'F',
            'mujer': 'F',
            'female': 'F',
            'otro': 'O',
            'o': 'O',
            '3': 'O',
        }
        
        df_std[columna_sexo] = df_std[columna_sexo].str.lower().str.strip().map(mapeo_sexo)
        
        # Mantener solo M, F, O y NaN
        df_std[columna_sexo] = df_std[columna_sexo].where(
            df_std[columna_sexo].isin(['M', 'F', 'O']),
            None
        )
        
        return df_std
    
    def estandarizar_edad(self, df: pd.DataFrame, columna_edad: str = "edad") -> pd.DataFrame:
        """
        Estandariza valores de edad (convierte a int, elimina negativos y extremos)
        
        Args:
            df: Dataframe
            columna_edad: Nombre de la columna de edad
            
        Returns:
            Dataframe con edad estandarizada
        """
        if columna_edad not in df.columns:
            return df
        
        df_std = df.copy()
        
        # Convertir a numérico
        df_std[columna_edad] = pd.to_numeric(df_std[columna_edad], errors='coerce')
        
        # Eliminar edades negativas y mayores a 150
        df_std.loc[(df_std[columna_edad] < 0) | (df_std[columna_edad] > 150), columna_edad] = None
        
        return df_std
    
    def estandarizar_municipio(self, df: pd.DataFrame, columna_municipio: str = "municipio") -> pd.DataFrame:
        """
        Estandariza nombres de municipio (mayúscula, sin espacios duplicados)
        
        Args:
            df: Dataframe
            columna_municipio: Nombre de la columna
            
        Returns:
            Dataframe con municipios estandarizados
        """
        if columna_municipio not in df.columns:
            return df
        
        df_std = df.copy()
        
        # Normalizar: mayúscula, trim, espacio simple
        df_std[columna_municipio] = (
            df_std[columna_municipio]
            .str.upper()
            .str.strip()
            .str.replace(r'\s+', ' ', regex=True)
        )
        
        return df_std


if __name__ == "__main__":
    print("=== PRUEBA DEL MÓDULO NORMALIZADOR_COLUMNAS ===")
    
    normalizador = NormalizadorColumnas()
    print("Normalizador de columnas inicializado")
