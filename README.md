# 🌍 GeoRaster to CAD | Extractor Georreferenciado Universal

Aplicación web desarrollada en **Streamlit** para automatizar la extracción y georreferenciación milimétrica para AutoCAD de **cualquier servidor WMS del mundo**, Google Satélite, Esri y servicios oficiales a partir de polilíneas cerradas de planos CAD (**DXF**), capas GIS Shapefile (**ZIP**), Google Earth (**KML/KMZ**) o polígonos dibujados a mano alzada en el mapa.

Permite descargar e insertar en **AutoCAD, AutoCAD Map 3D, Civil 3D y BricsCAD**:
- **⚙️ Agregar WMS externo**: Conexión directa a cualquier servidor WMS del mundo.
- **Camino de Santiago**: Trazados oficiales del Camino de Santiago (IGN).
- **Cartografía raster (MTN Topográfico - IGN)**: Mapa ráster MTN25/MTN50 oficial con curvas de nivel y toponimia.
- **Cuadrículas cartográficas**: Hojas y cuadrículas MTN oficiales del IGN.
- **Direcciones y Códigos Postales**: Callejero y códigos postales de CartoCiudad (IGN).
- **Esri World Imagery (Mundial - Alta Resolución)**: Satélite global de alta resolución.
- **Fototeca (Vuelos históricos IGN)**: Vuelos históricos de España (años 30, 40, vuelo americano 1956).
- **Google Híbrido (Mundial)**: Satélite con vías y toponimia sobreimpresas.
- **Google Satélite (Mundial - Máxima Resolución)**: Fotografía satelital mundial nítida.
- **Hidrografía - Información Geográfica de Referencia**: Red hidrográfica y masas de agua oficiales.
- **Hojas kilométricas (Madrid - 1860)**: Cartografía histórica parcelaria de Madrid y alrededores (1860).
- **Información sísmica (IGN)**: Epicentros de terremotos y sismicidad histórica y en tiempo real.
- **Mapa base (IGN Base)**: Cartografía continua integrada oficial de España.
- **Modelo Digital de Pendientes (MDP05)**: Mapa ráster de pendientes e inclinación del terreno.
- **Modelos Digitales del Terreno (Relieve LiDAR - IGN)**: Sombreado continuo de relieve LiDAR/MDT.
- **Mosaicos de Satélite históricos de España (Sentinel)**: Mosaicos multiespectrales estacionales Sentinel-2.
- **Nombres Geográficos (NGBE - IGN)**: Nomenclátor oficial y toponimia normalizada.
- **Ocupación de Suelo histórico (CORINE)**: Series históricas CORINE Land Cover y SIOSE.
- **Ocupación del Suelo (SIOSE)**: Coberturas y usos del suelo actuales.
- **Ortofotos históricas y PNOA anual**: Campañas aéreas ortofotográficas de años anteriores.
- **Ortofotos máxima actualidad del PNOA**: Vuelo ortofotográfico oficial de máxima resolución de España.
- **Ortofotos provisionales del PNOA**: Ortoimágenes rápidas provisionales y de emergencia.
- **Planimetrías (Minutas cartográficas)**: Planimetrías y altimetrías manuscritas del siglo XIX y principios del XX.
- **Primera edición MTN**: Primera edición histórica impresa del Mapa Topográfico Nacional.
- **Red de Transporte - IGR**: Redes viarias, ferroviarias y marítimo-aéreas oficiales.
- **Red de Vigilancia Volcánica del IGN**: Estaciones de vigilancia y monitoreo volcánico.
- **Redes geodésicas (IGN)**: Vértices geodésicos REGENTE, ROI, nivelación REDNAP y GNSS.
- **Unidades administrativas**: Límites oficiales de municipios, provincias y comunidades autónomas.

Genera directamente para cada polígono los archivos estándar:
- `.tif`: Imagen raster descargada del servicio en máxima resolución y nitidez nativa.
- `.tfw`: Archivo de calibración espacial (*World File*) con las coordenadas UTM/proyectadas exactas de georreferenciación.

### ✨ Características Principales:
- **📦 Carga de Shapefile (.ZIP)**: Admite la carga de archivos Shapefile comprimidos en `.zip` (que contengan sus componentes `.shp`, `.shx`, `.dbf` y `.prj`). Lee atributos de parcela/finca, extrae geometrías de polígono y detecta automáticamente la proyección cartográfica oficial desde el archivo `.prj`.
- **🧩 Mosaico Inteligente y Fusión en 1 Clic**: Para ámbitos grandes, la aplicación divide automáticamente la descarga en teselas a máxima resolución nativa (0.50 m/px) respetando los límites de los servidores WMS, e incluye un botón en los resultados para **ensamblar las teselas en una sola imagen continua (.tif + .tfw)** directamente en memoria RAM sin descargas adicionales.
- **🧠 Detección y Recomendación Automática de EPSG/CRS**: Al subir cualquier plano DXF o Shapefile, el sistema analiza instantáneamente sus coordenadas métricas $(X, Y)$, capas y metadatos, detectando la proyección recomendada (ej: Australia `EPSG:7855` / `7856`, España `EPSG:25830`, Colombia `EPSG:9377`, Canarias `EPSG:32628`, etc.) con un botón de **1-clic** para aplicarla y volar el visor satelital a la posición real.
- **🌐 Desplegable Completo de EPSG (>7.200 Sistemas Mundiales)**: Acceso directo e instantáneo a todo el catálogo geodésico mundial oficial de códigos EPSG (>7.200 sistemas de proyección y marcos de referencia) mediante un desplegable interactivo con búsqueda predictiva en tiempo real por número, país o nombre. Incluye filtros rápidos para sistemas Populares, España, América Latina o el catálogo global completo.
- **➕ Instalador de Códigos EPSG y Proyecciones Personalizadas**: Posibilidad de registrar e instalar de forma persistente nuevos códigos EPSG o definiciones personalizadas (WKT / PROJ.4) con nombres de proyecto a medida, guardándolos automáticamente en tu lista para reutilizarlos en cualquier momento.
- **🗺️ Catálogo Multicartográfico Universal**: Elige entre Google Satélite, Google Híbrido, Esri World Imagery, cualquier WMS propio, PNOA o cartografía IGN con un solo clic.
- **🪄 Recomendación Inteligente de Calidad por Área**: Calcula la resolución óptima ($m/px$) analizando la superficie de cada polígono (< 0.5 ha = 0.25 m/px, 0.5 a 2.5 ha = 0.50 m/px, 2.5 a 15 ha = 1.00 m/px, etc.).
- **🗺️ Visor de Ubicación con Encuadre de Salida**: Muestra en el mapa interactivo tanto la geometría CAD como el recuadro rectangular exacto de la imagen TIF que se descargará con el buffer perimetral, permitiendo conmutar entre satélite, WMS y cartografía.
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
- **`requirements.txt`**: Librerías necesarias (`streamlit`, `ezdxf`, `shapely`, `pyproj`, `requests`, `pandas`, `folium`, `pillow`, `pyshp`).
- **`.streamlit/config.toml`**: Configuración de tema visual y servidor web.
- **`iniciar_app.bat`**: Lanzador local para pruebas en Windows.
- **`subir_a_github.bat`**: Script para subir cambios a GitHub con un solo clic.

---

## 🧭 Inserción en AutoCAD en posición UTM exacta
- **En AutoCAD Map 3D / Civil 3D / BricsCAD (Recomendado):**
  1. Descomprime el archivo `.zip` en la carpeta de tu proyecto.
  2. Ejecuta el comando `_MAPIINSERT` (o ve a *Insertar* -> *Imagen ráster*).
  3. Selecciona los archivos `.tif` descargados.
  4. AutoCAD detectará automáticamente los archivos `.tfw` asociados y colocará las ortofotos en sus coordenadas UTM reales sin necesidad de mover ni escalar.
- **En AutoCAD Clásico / LT:**
  1. Utiliza el comando `_IMAGEATTACH` (`ENLAZARIMG`).
- **Recorte de minutas o ámbitos inclinados (`DELIMIMG`):**
  1. Ejecuta el comando `_IMAGECLIP` (o `DELIMIMG`).
  2. Selecciona la imagen ráster.
  3. Elige la opción *Nuevo contorno* (`N`) y luego *Seleccionar polilínea* (`S`).
  4. Toca tu polilínea cerrada: AutoCAD ocultará los bordes sobrantes al instante manteniendo la georreferenciación perfecta.
