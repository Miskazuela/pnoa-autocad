# 📐 Cartografía & PNOA to AutoCAD | Extractor Georreferenciado Oficial

Aplicación web desarrollada en **Streamlit** para automatizar la extracción de cartografía oficial y ortofotografías aéreas de máxima resolución de España a partir de polilíneas cerradas de planos CAD (**DXF**).

Permite descargar e insertar en **AutoCAD, AutoCAD Map 3D, Civil 3D y BricsCAD**:
- **🇪🇸 Ortofoto Aérea PNOA (IGN)**: Fotografías aéreas y satelitales oficiales de España de máxima nitidez.
- **🌍 Google Satélite (Mundial)**: Fotografía satelital mundial de alta resolución de Google sin rótulos.
- **🌍 Google Híbrido (Mundial)**: Satélite de Google con carreteras, calles principales y toponimia sobreimpresas.
- **🛰️ Esri World Imagery (Mundial)**: Ortofotografía satelital global de alta resolución de Esri.
- **🗺️ Mapa Ráster IGN (MTN25 / MTN50 Topográfico)**: Cartografía topográfica oficial con curvas de nivel, toponimia y altitudes (`https://www.ign.es/wmts/mapa-raster`).
- **🏔️ Modelo Digital del Terreno - Relieve (MDT / LiDAR)**: Sombreado continuo de pendientes y relieve.
- **⚙️ Personalizado**: Conexión a cualquier servicio WMS 1.3.0 oficial o autonómico.

Genera directamente para cada polígono los archivos estándar:
- `.tif`: Imagen raster descargada del servicio en máxima resolución y nitidez nativa.
- `.tfw`: Archivo de calibración espacial (*World File*) con las coordenadas UTM exactas de georreferenciación.

### ✨ Características Principales:
- **🗺️ Catálogo Multicartográfico Oficial y Satelital**: Elige entre Ortofoto PNOA, Google Satélite, Google Híbrido, Esri World Imagery, Mapa Topográfico Ráster MTN o Relieve MDT con un solo clic.
- **🪄 Recomendación Inteligente de Calidad por Área**: Calcula la resolución óptima ($m/px$) analizando la superficie de cada polígono (< 0.5 ha = 0.25 m/px, 0.5 a 2.5 ha = 0.50 m/px, 2.5 a 15 ha = 1.00 m/px, etc.).
- **🗺️ Visor de Ubicación con Encuadre de Salida**: Muestra en el mapa interactivo tanto la geometría CAD como el recuadro rectangular exacto de la imagen TIF que se descargará con el buffer perimetral, permitiendo conmutar entre satélite, PNOA, mapa ráster y relieve.
- **✂️ Recorte de Minutas en AutoCAD (`DELIMIMG`)**: La aplicación entrega el ráster ortogonal puro y nítido. Para recortarlo por una minuta inclinada en AutoCAD, se utiliza el comando nativo `_IMAGECLIP` (`DELIMIMG`), ajustándose al polígono sin perder calidad ni lidiar con fondos negros.
- **📦 Salida Limpia**: Solo descarga los productos necesarios (`.tif` + `.tfw`).

---

## 🌐 Despliegue en la Nube (Streamlit Community Cloud)

Esta aplicación está lista para funcionar online en **Streamlit Community Cloud**:
1. Entra en [share.streamlit.io](https://share.streamlit.io/) e inicia sesión con tu GitHub.
2. Selecciona el repositorio `Miskazuela/pnoa-autocad`, rama `main` y archivo principal `app.py`.
3. Haz clic en **Deploy**.
4. ¡Cualquier persona puede usar la aplicación directamente desde su navegador web sin instalar nada!

---

## 🚀 Ejecución en Local (Desarrollo y Pruebas)

### Opción 1: Doble clic (Windows)
Haz doble clic sobre:
```text
iniciar_app.bat
```
Esto abrirá automáticamente la aplicación en tu navegador en `http://localhost:8501`.

### Opción 2: Desde terminal / PowerShell
```bash
pip install -r requirements.txt
python -m streamlit run app.py
```

---

## 📂 Archivos en esta carpeta
- **`app.py`**: Código fuente principal de la aplicación web en Streamlit.
- **`ejemplo_madrid.dxf`**: Plano de prueba con 3 parcelas cerradas en Madrid (`EPSG:25830`) para probar la app de inmediato.
- **`requirements.txt`**: Librerías necesarias (`streamlit`, `ezdxf`, `shapely`, `pyproj`, `requests`, `pandas`, `folium`, `pillow`).
- **`.streamlit/config.toml`**: Configuración de tema visual y servidor web.
- **`iniciar_app.bat`**: Lanzador local para pruebas en Windows.
- **`subir_a_github.bat`**: Script para subir cambios a GitHub con un solo clic.

---

## 🧭 Inserción en AutoCAD en posición UTM exacta
- **En AutoCAD Map 3D / Civil 3D:**
  1. Ejecuta el comando `_MAPIINSERT` (o ve a *Insertar* -> *Imagen ráster*).
  2. Selecciona el archivo `.tif` descargado.
  3. AutoCAD detectará automáticamente el archivo `.tfw` asociado y colocará la ortofoto en sus coordenadas reales sin necesidad de mover ni escalar.
- **En AutoCAD Clásico / LT:**
  1. Utiliza el comando `_IMAGEATTACH` (`ENLAZARIMG`).
