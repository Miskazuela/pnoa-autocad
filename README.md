# 📐 Cartografía & PNOA to AutoCAD | Extractor Georreferenciado Oficial

Aplicación web desarrollada en **Streamlit** para automatizar la extracción de cartografía oficial y ortofotografías aéreas de máxima resolución de España a partir de polilíneas cerradas de planos CAD (**DXF**).

Permite descargar e insertar en **AutoCAD, AutoCAD Map 3D, Civil 3D y BricsCAD**:
- **🇪🇸 Ortofoto Aérea PNOA (IGN)**: Fotografías aéreas y satelitales de máxima nitidez.
- **🗺️ Mapa Ráster IGN (MTN25 / MTN50 Topográfico)**: Cartografía topográfica oficial con curvas de nivel, toponimia y altitudes (`https://www.ign.es/wmts/mapa-raster`).
- **🏔️ Modelo Digital del Terreno - Relieve (MDT / LiDAR)**: Sombreado continuo de pendientes y relieve.
- **⚙️ Personalizado**: Conexión a cualquier servicio WMS 1.3.0 oficial o autonómico.

Genera directamente para cada polígono los archivos estándar:
- `.tif`: Imagen raster descargada del servicio oficial en máxima resolución y nitidez nativa.
- `.tfw`: Archivo de calibración espacial (*World File*) con las coordenadas UTM exactas de georreferenciación.

### ✨ Características Principales:
- **🗺️ Catálogo Multicartográfico del IGN**: Elige entre Ortofoto PNOA, Mapa Topográfico Ráster MTN o Relieve MDT con un solo clic.
- **🪄 Recomendación Inteligente de Calidad por Área**: Calcula la resolución óptima ($m/px$) analizando la superficie de cada polígono (< 0.5 ha = 0.25 m/px, 0.5 a 2.5 ha = 0.50 m/px, 2.5 a 15 ha = 1.00 m/px, etc.).
- **🗺️ Visor de Ubicación con Encuadre de Salida**: Muestra en el mapa interactivo tanto la geometría CAD como el recuadro rectangular exacto de la imagen TIF que se descargará con el buffer perimetral, permitiendo conmutar entre satélite, PNOA, mapa ráster y relieve.
- **✂️ Recorte de Minutas en AutoCAD (`DELIMIMG`)**: La aplicación entrega el ráster ortogonal puro y nítido. Para recortarlo por una minuta inclinada en AutoCAD, se utiliza el comando nativo `_IMAGECLIP` (`DELIMIMG`), ajustándose al polígono sin perder calidad ni lidiar con fondos negros.
- **📦 Salida Limpia**: Solo descarga los productos necesarios (`.tif` + `.tfw`).

---

## 🚀 Cómo iniciar la aplicación

### Opción 1: Ejecutable nativo Windows (Recomendada para usuarios)
Haz doble clic sobre el archivo:
```text
PNOA_AutoCAD.exe
```
Se abrirá una pequeña ventana de control y automáticamente tu navegador web predeterminado cargará la aplicación en `http://localhost:8501`.

### Opción 2: Mediante lanzador `.bat` (Auto-configurable)
Haz doble clic sobre:
```text
iniciar_app.bat
```
> [!TIP]
> Si el equipo no tiene Python instalado, `iniciar_app.bat` descargará y configurará automáticamente un entorno portable ligero de forma silenciosa. ¡No necesitas instalar Python ni configurar el PATH!

### Opción 3: Desde la terminal / PowerShell
Si prefieres ejecutarlo manualmente con tu propio entorno:
```bash
python -m streamlit run app.py
```

---

## 💼 Distribuir Versión Portable a otros usuarios (.ZIP)
Si deseas compartir la aplicación con clientes, topógrafos o compañeros que no tienen Python ni conexión para configurar dependencias:
1. Haz doble clic en `crear_version_portable.bat`.
2. Se generará en la carpeta `dist/` el archivo **`PNOA_to_AutoCAD_Portable.zip`**.
3. Sube ese `.zip` a las **Releases** de tu GitHub o compártelo por OneDrive / red local. Quien lo descargue solo tiene que descomprimir y hacer doble clic en `PNOA_AutoCAD.exe`.

---

## 📂 Archivos en esta carpeta
- **`PNOA_AutoCAD.exe`**: Lanzador nativo de Windows (sin ventanas negras de consola).
- **`iniciar_app.bat`**: Lanzador por lotes con instalador portable automático en caso de no detectar Python.
- **`crear_version_portable.bat`**: Generador automático del paquete `.zip` independiente para GitHub Releases.
- **`app.py`**: Código fuente principal de la aplicación web en Streamlit.
- **`ejemplo_madrid.dxf`**: Plano de prueba con 3 parcelas cerradas en Madrid (`EPSG:25830`) para probar la app de inmediato.
- **`requirements.txt`**: Librerías necesarias (`streamlit`, `ezdxf`, `shapely`, `pyproj`, `requests`, `pandas`, `folium`, `pillow`).
- **`.streamlit/config.toml`**: Configuración de tema visual y servidor web.

---

## 🧭 Inserción en AutoCAD en posición UTM exacta
- **En AutoCAD Map 3D / Civil 3D:**
  1. Ejecuta el comando `_MAPIINSERT` (o ve a *Insertar* -> *Imagen ráster*).
  2. Selecciona el archivo `.tif` descargado.
  3. AutoCAD detectará automáticamente el archivo `.tfw` asociado y colocará la ortofoto en sus coordenadas reales sin necesidad de mover ni escalar.
- **En AutoCAD Clásico / LT:**
  1. Utiliza el comando `_IMAGEATTACH` (`ENLAZARIMG`).
