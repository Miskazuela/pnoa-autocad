# 📐 PNOA to AutoCAD | Extractor de Ortofotos Georreferenciadas

Aplicación web desarrollada en **Streamlit** para automatizar la extracción de ortofotografías aéreas de máxima resolución del **PNOA (Plan Nacional de Ortofotografía Aérea - IGN España)** a partir de polilíneas cerradas de planos CAD (**DXF**).

Genera directamente para cada polígono la tríada de georreferenciación estándar para **AutoCAD, AutoCAD Map 3D, Civil 3D y BricsCAD**:
- `.tif`: Imagen aérea raster descargada del servicio WMS INSPIRE del IGN.
- `.tfw`: Archivo de calibración espacial (*World File*) con las coordenadas de georreferenciación exactas.
- `.prj`: Definición de proyección cartográfica en formato WKT.

---

## 🚀 Cómo iniciar la aplicación

### Opción 1: Doble clic (Recomendada en Windows)
Haz doble clic sobre el archivo ejecutable:
```text
iniciar_app.bat
```
Esto abrirá automáticamente la aplicación en tu navegador web predeterminado en `http://localhost:8501`.

### Opción 2: Desde la terminal / PowerShell
Abre PowerShell o CMD en esta carpeta (`C:\Users\JMN\Documents\PNOA`) y ejecuta:
```bash
python -m streamlit run app.py
```

---

## 📦 Instalación de dependencias (si configuras otro equipo)
```bash
pip install -r requirements.txt
```

---

## 📂 Archivos en esta carpeta
- **`app.py`**: Código fuente principal de la aplicación web en Streamlit.
- **`iniciar_app.bat`**: Lanzador directo para Windows con un solo clic.
- **`ejemplo_madrid.dxf`**: Plano de prueba con 3 parcelas cerradas en Madrid (`EPSG:25830`) para probar la app de inmediato.
- **`requirements.txt`**: Librerías Python necesarias (`streamlit`, `ezdxf`, `shapely`, `pyproj`, `requests`, `pandas`).
- **`.streamlit/config.toml`**: Configuración de tema y servidor web.

---

## 🧭 Inserción en AutoCAD en posición UTM exacta
- **En AutoCAD Map 3D / Civil 3D:**
  1. Ejecuta el comando `_MAPIINSERT` (o ve a *Insertar* -> *Imagen ráster*).
  2. Selecciona el archivo `.tif` descargado.
  3. AutoCAD detectará automáticamente el archivo `.tfw` asociado y colocará la ortofoto en sus coordenadas reales sin necesidad de mover ni escalar.
- **En AutoCAD Clásico / LT:**
  1. Utiliza el comando `_IMAGEATTACH` (`ENLAZARIMG`).
