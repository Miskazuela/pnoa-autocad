"""
========================================================================================
Aplicación Web: Extractor de Ortofotos PNOA (España) para AutoCAD
Desarrollador: Especialista SIG y Desarrollador Senior en Python
Descripción:
    Automatiza la extracción de ortofotografías aéreas georreferenciadas de máxima
    resolución del Plan Nacional de Ortofotografía Aérea (IGN PNOA) a partir de
    polilíneas cerradas delimitadas en planos CAD (.dxf).
    
    Genera para cada polígono la georreferenciación estándar requerida
    por AutoCAD, AutoCAD Map 3D, Civil 3D y BricsCAD:
      1. {nombre}.tif -> Imagen raster descargada del servicio WMS.
      2. {nombre}.tfw -> Archivo de calibración espacial (World File) con coordenadas exactas.

    Incluye:
      - Visor cartográfico interactivo (Satélite y PNOA WMS) para verificar la ubicación del DXF.
      - Sistema de resolución DNS ultra-resiliente (DoH fallback) para prevenir errores
        transitorios de red [Errno 11002 getaddrinfo failed] con www.ign.es.
      - Control estricto de límites de MapServer (máx. 4096 px) y modo mosaico/teselas continuo.

Comando de instalación de dependencias:
    pip install streamlit ezdxf shapely pyproj requests pandas folium streamlit-folium

Comando para ejecutar la aplicación:
    streamlit run app.py
========================================================================================
"""

import io
import os
import re
import ssl
import json
import math
import socket
import zipfile
import urllib.request
import traceback
import concurrent.futures
from typing import List, Dict, Any, Tuple, Optional

import streamlit as st
import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry
import ezdxf
from shapely.geometry import Polygon
from pyproj import CRS, Transformer
import folium
from streamlit_folium import st_folium
from PIL import Image, ImageDraw, ImageChops

# Streamlit Page Config debe ser la primera llamada de Streamlit
st.set_page_config(
    page_title="GeoRaster to CAD | Extractor Georreferenciado Universal",
    page_icon="🌍",
    layout="wide",
    initial_sidebar_state="expanded"
)


# --------------------------------------------------------------------------------------
# 0. SISTEMA DE RESOLUCIÓN DNS ULTRA-RESILIENTE (DOH FALLBACK PARA IGN EN WINDOWS)
# --------------------------------------------------------------------------------------
if os.name == "nt" and not getattr(socket, "_is_resilient_dns_patched", False):
    _orig_getaddrinfo = socket.getaddrinfo
    _dns_cache: Dict[str, str] = {}
    _KNOWN_IGN_IPS = [
        "3.166.160.90",
        "3.166.160.37",
        "3.166.160.84",
        "3.166.160.66",
        "18.173.166.12",
        "18.173.166.45"
    ]

    def _resolve_host_fallback(hostname: str) -> Optional[str]:
        host_lower = str(hostname).lower()
        if not hostname or ("ign.es" not in host_lower and "idee.es" not in host_lower):
            return None
        if hostname in _dns_cache:
            return _dns_cache[hostname]
        
        # 1. Resolver vía Google DoH directamente a la IP 8.8.8.8 (sin requerir DNS local)
        try:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            req = urllib.request.Request(
                f"https://8.8.8.8/resolve?name={hostname}&type=A",
                headers={"Host": "dns.google", "User-Agent": "curl/7.68.0"}
            )
            with urllib.request.urlopen(req, timeout=4, context=ctx) as r:
                data = json.loads(r.read().decode())
                for item in data.get("Answer", []):
                    if item.get("type") == 1:
                        ip = item.get("data")
                        _dns_cache[hostname] = ip
                        return ip
        except Exception:
            pass

        # 2. Resolver vía Cloudflare DoH directamente a la IP 1.1.1.1
        try:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            req = urllib.request.Request(
                f"https://1.1.1.1/dns-query?name={hostname}&type=A",
                headers={"Accept": "application/dns-json", "User-Agent": "curl/7.68.0"}
            )
            with urllib.request.urlopen(req, timeout=4, context=ctx) as r:
                data = json.loads(r.read().decode())
                for item in data.get("Answer", []):
                    if item.get("type") == 1:
                        ip = item.get("data")
                        _dns_cache[hostname] = ip
                        return ip
        except Exception:
            pass

        # 3. Fallback estático de IPs CloudFront del IGN
        if "ign.es" in hostname.lower():
            ip = _KNOWN_IGN_IPS[0]
            _dns_cache[hostname] = ip
            return ip

        return None

    def _resilient_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
        try:
            return _orig_getaddrinfo(host, port, family, type, proto, flags)
        except socket.gaierror as e:
            fallback_ip = _resolve_host_fallback(str(host))
            if fallback_ip:
                return _orig_getaddrinfo(fallback_ip, port, socket.AF_INET, type, proto, flags)
            raise e

    socket.getaddrinfo = _resilient_getaddrinfo
    socket._is_resilient_dns_patched = True


# --------------------------------------------------------------------------------------
# 1. UTILIDADES Y SANITIZACIÓN DE NOMBRES
# --------------------------------------------------------------------------------------
def sanitize_filename(name: str) -> str:
    """
    Sanitiza nombres de archivo reemplazando caracteres especiales, tildes y espacios
    por guiones bajos, asegurando compatibilidad multiplataforma y con AutoCAD.
    """
    if not name:
        return "ortofoto"
    clean = re.sub(r"[^\w\-]", "_", str(name).strip())
    clean = re.sub(r"_+", "_", clean).strip("_")
    return clean or "ortofoto"


def create_resilient_session(timeout: int = 35) -> requests.Session:
    """
    Crea una sesión HTTP con reintentos exponenciales automáticos para mitigar caídas.
    """
    session = requests.Session()
    retries = Retry(
        total=5,
        backoff_factor=1.5,
        status_forcelist=[429, 500, 502, 503, 504],
        raise_on_status=False
    )
    adapter = HTTPAdapter(max_retries=retries)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


# --------------------------------------------------------------------------------------
# 2. LECTURA Y EXTRACCIÓN DE POLÍGONOS CAD (ezdxf & shapely)
# --------------------------------------------------------------------------------------
def load_dxf_document(file_bytes: bytes) -> ezdxf.document.Drawing:
    """
    Carga de forma robusta un archivo DXF desde memoria, normalizando saltos de línea (CRLF)
    y gestionando codificaciones comunes de planos AutoCAD en España (UTF-8, CP1252, Latin-1).
    """
    for encoding in ["utf-8", "cp1252", "latin-1", "iso-8859-1"]:
        try:
            raw_text = file_bytes.decode(encoding, errors="surrogateescape")
            normalized_text = raw_text.replace("\r\n", "\n").replace("\r", "\n")
            doc = ezdxf.read(io.StringIO(normalized_text))
            return doc
        except Exception:
            continue

    try:
        doc, _ = ezdxf.recover.read(io.BytesIO(file_bytes))
        return doc
    except Exception as err:
        raise ValueError(f"No fue posible interpretar el archivo DXF: {err}")


def get_recommended_resolution(area_m2: float) -> Tuple[float, str, str]:
    """
    Calcula la resolución óptima recomendada (m/px) en función del tamaño del área (m²):
      - < 5.000 m² (< 0.5 ha): 0.25 m/px - Muy Alta (Edificación, solares y detalle máximo)
      - 5.000 a 25.000 m² (0.5 a 2.5 ha): 0.50 m/px - Alta (Parcelas residenciales / naves)
      - 25.000 a 150.000 m² (2.5 a 15 ha): 1.00 m/px - Estándar (Urbanizaciones y obras civiles)
      - 150.000 a 1.000.000 m² (15 a 100 ha): 2.00 m/px - Normal (Grandes fincas rústicas)
      - > 1.000.000 m² (> 100 ha): 4.00 m/px - Panorámica (Escala comarcal y territorial)
    """
    if area_m2 < 5000:
        return 0.25, "0.25 m/px (Muy Alta)", "Solares y edificación (< 0.5 ha)"
    elif area_m2 < 25000:
        return 0.50, "0.50 m/px (Alta)", "Parcelas y naves (0.5 a 2.5 ha)"
    elif area_m2 < 150000:
        return 1.00, "1.00 m/px (Estándar)", "Urbanizaciones y obras (2.5 a 15 ha)"
    elif area_m2 < 1000000:
        return 2.00, "2.00 m/px (Normal)", "Grandes fincas e infraestructuras (15 a 100 ha)"
    else:
        return 4.00, "4.00 m/px (Panorámica)", "Escala territorial (> 100 ha)"


def parse_dxf_polygons(file_bytes: bytes, filename: str, service_tag: str = "pnoa") -> List[Dict[str, Any]]:
    """
    Extrae todas las polilíneas cerradas (LWPOLYLINE y POLYLINE con closed=True)
    del espacio modelo del DXF y calcula su Bounding Box, área y vértices.
    """
    doc = load_dxf_document(file_bytes)
    msp = doc.modelspace()
    
    extracted_polygons: List[Dict[str, Any]] = []
    base_file_prefix = os.path.splitext(sanitize_filename(filename))[0]
    polygon_counter = 1

    for entity in msp.query("LWPOLYLINE POLYLINE"):
        try:
            dxftype = entity.dxftype()
            layer = getattr(entity.dxf, "layer", "0")
            pts: List[Tuple[float, float]] = []

            if dxftype == "LWPOLYLINE":
                pts = [(float(p[0]), float(p[1])) for p in entity.get_points("xy")]
            elif dxftype == "POLYLINE":
                pts = [(float(p.x), float(p.y)) for p in entity.points()]

            if len(pts) < 3:
                continue

            is_cad_closed = bool(entity.is_closed)
            is_geom_closed = (abs(pts[0][0] - pts[-1][0]) < 1e-5 and abs(pts[0][1] - pts[-1][1]) < 1e-5)

            if not (is_cad_closed or is_geom_closed):
                continue

            poly = Polygon(pts)
            minx, miny, maxx, maxy = poly.bounds
            width = maxx - minx
            height = maxy - miny

            if width <= 0.001 or height <= 0.001:
                continue

            clean_layer = sanitize_filename(layer)
            clean_tag = sanitize_filename(service_tag)
            output_name = f"{base_file_prefix}_{clean_tag}_{clean_layer}_p{polygon_counter}"

            # Calcular resolución recomendada según el tamaño de la superficie
            rec_res, rec_label, _ = get_recommended_resolution(poly.area)

            extracted_polygons.append({
                "incluir": True,
                "id": polygon_counter,
                "capa": layer,
                "nombre_archivo": output_name,
                "resolucion_m_px": rec_res,
                "calidad_sugerida": rec_label,
                "ancho_m": round(width, 2),
                "alto_m": round(height, 2),
                "area_m2": round(poly.area, 2),
                "num_vertices": len(pts),
                "bounds": (minx, miny, maxx, maxy),
                "pts": pts
            })
            polygon_counter += 1

        except Exception:
            continue

    return extracted_polygons


# --------------------------------------------------------------------------------------
# 3. CATÁLOGO DE SERVICIOS CARTOGRÁFICOS Y SATELITALES (MUNDIAL Y NACIONAL)
# --------------------------------------------------------------------------------------
SERVICES_CATALOG: Dict[str, Dict[str, Any]] = {
    "google_sat": {
        "name": "🌍 Google Satélite (Mundial - Máxima Resolución)",
        "type": "xyz",
        "url": "https://{s}.google.com/vt/lyrs=s&x={x}&y={y}&z={z}",
        "layer": "",
        "tag": "google_sat",
        "badge": "Google Satélite",
        "description": "Fotografía satelital mundial de Google de alta resolución sin rótulos. Cobertura global (Australia, América, Europa, Asia y resto del mundo).",
        "folium_name": "🌍 Google Satélite (Google Maps)",
    },
    "google_hybrid": {
        "name": "🌍 Google Híbrido (Mundial - Satélite + Vías y Nombres)",
        "type": "xyz",
        "url": "https://{s}.google.com/vt/lyrs=y&x={x}&y={y}&z={z}",
        "layer": "",
        "tag": "google_hybrid",
        "badge": "Google Híbrido",
        "description": "Satélite de Google con red de carreteras, calles principales y toponimia sobreimpresas.",
        "folium_name": "🌍 Google Híbrido (Satélite + Vías)",
    },
    "esri_sat": {
        "name": "🛰️ Esri World Imagery (Mundial - Alta Resolución)",
        "type": "xyz",
        "url": "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        "layer": "",
        "tag": "esri_sat",
        "badge": "Esri Satélite",
        "description": "Ortofotografía satelital global de Esri / Maxar de alta resolución.",
        "folium_name": "🛰️ Esri World Imagery",
    },
    "custom": {
        "name": "⚙️ Servidor WMS Universal (Cualquier país / organismo del mundo)",
        "type": "wms",
        "url": "https://www.ign.es/wms-inspire/pnoa-ma",
        "layer": "OI.OrthoimageCoverage",
        "tag": "wms_custom",
        "badge": "WMS Universal",
        "description": "Introduce la URL y capa de cualquier servidor WMS del mundo (gobiernos estatales, catastro, Australia, etc.).",
        "folium_name": "⚙️ WMS Universal",
    },
    "pnoa": {
        "name": "🇪🇸 IGN - Ortofoto Aérea PNOA (España - Máxima Resolución)",
        "type": "wms",
        "url": "https://www.ign.es/wms-inspire/pnoa-ma",
        "layer": "OI.OrthoimageCoverage",
        "tag": "pnoa",
        "badge": "Ortofoto PNOA",
        "description": "Ortofotografías aéreas oficiales de España de máxima resolución del PNOA. Ideal para urbanismo y edificación.",
        "folium_name": "🇪🇸 Ortofoto PNOA WMS (IGN)",
    },
    "mapa_raster": {
        "name": "🗺️ IGN - Mapa Ráster / MTN Topográfico (España)",
        "type": "wms",
        "url": "https://www.ign.es/wms-inspire/mapa-raster",
        "layer": "mtn_rasterizado",
        "tag": "mtn_raster",
        "badge": "Mapa Ráster MTN",
        "description": "Cartografía topográfica oficial con curvas de nivel, toponimia y altitudes.",
        "folium_name": "🗺️ IGN Mapa Ráster MTN Topográfico",
    },
    "mdt_relieve": {
        "name": "🏔️ IGN - Modelo Digital del Terreno Relieve (España)",
        "type": "wms",
        "url": "https://servicios.idee.es/wms-inspire/mdt",
        "layer": "EL.GridCoverage",
        "tag": "mdt_relieve",
        "badge": "Relieve MDT",
        "description": "Sombreado continuo del terreno derivado de LiDAR y MDT para estudios de pendiente.",
        "folium_name": "🏔️ IGN Relieve Sombreado MDT",
    }
}


def compute_georeferencing_parameters(
    bounds: Tuple[float, float, float, float],
    buffer_pct: float,
    pixel_size: float,
    max_pixels_lado: int = 4000,
    max_pixels_totales: int = 16000000
) -> Dict[str, Any]:
    """
    Calcula el Bounding Box expandido por el buffer porcentual, pre-valida y escala
    las dimensiones en píxeles garantizando que NUNCA superen el límite de 4096 px
    impuesto por el servidor MapServer del IGN PNOA.
    """
    minx, miny, maxx, maxy = bounds

    # 1 & 2: Buffer porcentual
    dx = (maxx - minx) * buffer_pct
    dy = (maxy - miny) * buffer_pct
    bbox_buf = (minx - dx, miny - dy, maxx + dx, maxy + dy)
    width_m = bbox_buf[2] - bbox_buf[0]
    height_m = bbox_buf[3] - bbox_buf[1]

    # Forzar límite estricto del servidor WMS del IGN (máx. 4096 px)
    # Capped en 4000 px para evitar fallos por redondeo
    server_max_side = min(int(max_pixels_lado), 4000)
    server_max_total = min(int(max_pixels_totales), 16000000)

    ancho_px_ideal = width_m / pixel_size
    alto_px_ideal = height_m / pixel_size

    factor = min(
        server_max_side / ancho_px_ideal,
        server_max_side / alto_px_ideal,
        (server_max_total / (ancho_px_ideal * alto_px_ideal)) ** 0.5,
        1.0
    )

    ancho_px = min(server_max_side, max(1, round(ancho_px_ideal * factor)))
    alto_px = min(server_max_side, max(1, round(alto_px_ideal * factor)))

    pixel_x = width_m / ancho_px
    pixel_y = - (height_m / alto_px)
    x_center_ul = bbox_buf[0] + (pixel_x / 2.0)
    y_center_ul = bbox_buf[3] + (pixel_y / 2.0)

    tfw_content = (
        f"{pixel_x:.10f}\n"
        f"0.0000000000\n"
        f"0.0000000000\n"
        f"{pixel_y:.10f}\n"
        f"{x_center_ul:.10f}\n"
        f"{y_center_ul:.10f}\n"
    )

    return {
        "bbox_buf": bbox_buf,
        "width_m": width_m,
        "height_m": height_m,
        "ancho_px": ancho_px,
        "alto_px": alto_px,
        "pixel_x": pixel_x,
        "pixel_y": pixel_y,
        "tfw_content": tfw_content,
        "scaled": factor < 0.999,
        "factor": factor,
        "ancho_px_ideal": ancho_px_ideal,
        "alto_px_ideal": alto_px_ideal,
        "tile_suffix": ""
    }


def compute_tiled_georeferencing(
    bounds: Tuple[float, float, float, float],
    buffer_pct: float,
    pixel_size: float,
    max_tile_side: int = 4000
) -> List[Dict[str, Any]]:
    """
    Subdivide un Bounding Box extenso en una cuadrícula continua de teselas contiguas
    de máximo 4000 px cada una, preservando exactamente la resolución de píxel solicitada.
    """
    minx, miny, maxx, maxy = bounds
    dx = (maxx - minx) * buffer_pct
    dy = (maxy - miny) * buffer_pct
    bbox_buf = (minx - dx, miny - dy, maxx + dx, maxy + dy)
    width_m = bbox_buf[2] - bbox_buf[0]
    height_m = bbox_buf[3] - bbox_buf[1]

    ancho_px_ideal = width_m / pixel_size
    alto_px_ideal = height_m / pixel_size

    # Si cabe en una sola imagen de <= 4000 px, retornar una sola
    if ancho_px_ideal <= max_tile_side and alto_px_ideal <= max_tile_side:
        res = compute_georeferencing_parameters(bounds, buffer_pct, pixel_size, max_tile_side)
        res["tile_suffix"] = ""
        return [res]

    nx = max(1, math.ceil(ancho_px_ideal / max_tile_side))
    ny = max(1, math.ceil(alto_px_ideal / max_tile_side))

    tiles = []
    tile_w_m = width_m / nx
    tile_h_m = height_m / ny

    for r in range(ny):
        for c in range(nx):
            sub_minx = bbox_buf[0] + c * tile_w_m
            sub_maxx = sub_minx + tile_w_m
            sub_maxy = bbox_buf[3] - r * tile_h_m
            sub_miny = sub_maxy - tile_h_m

            w_px = min(max_tile_side, max(1, round(tile_w_m / pixel_size)))
            h_px = min(max_tile_side, max(1, round(tile_h_m / pixel_size)))

            pix_x = tile_w_m / w_px
            pix_y = - (tile_h_m / h_px)
            x_c = sub_minx + (pix_x / 2.0)
            y_c = sub_maxy + (pix_y / 2.0)

            tfw = (
                f"{pix_x:.10f}\n"
                f"0.0000000000\n"
                f"0.0000000000\n"
                f"{pix_y:.10f}\n"
                f"{x_c:.10f}\n"
                f"{y_c:.10f}\n"
            )

            tiles.append({
                "bbox_buf": (sub_minx, sub_miny, sub_maxx, sub_maxy),
                "width_m": tile_w_m,
                "height_m": tile_h_m,
                "ancho_px": w_px,
                "alto_px": h_px,
                "pixel_x": pix_x,
                "pixel_y": pix_y,
                "tfw_content": tfw,
                "scaled": False,
                "tile_suffix": f"_t{r+1}_{c+1}" if (nx > 1 or ny > 1) else ""
            })

    return tiles


def fetch_wms_ortho(
    session: requests.Session,
    wms_url: str,
    wms_layer: str,
    crs_str: str,
    bbox_buf: Tuple[float, float, float, float],
    ancho_px: int,
    alto_px: int,
    timeout: int = 35
) -> bytes:
    """
    Ejecuta la petición HTTP GetMap bajo el estándar OGC WMS 1.3.0 y valida
    rigurosamente que la respuesta sea una imagen TIFF válida y no un XML de error.
    """
    # Seguridad absoluta: asegurar que nunca se envíe > 4096 px al servidor
    ancho_px = min(4000, max(1, int(ancho_px)))
    alto_px = min(4000, max(1, int(alto_px)))

    params = {
        "SERVICE": "WMS",
        "VERSION": "1.3.0",
        "REQUEST": "GetMap",
        "LAYERS": wms_layer,
        "STYLES": "",
        "FORMAT": "image/tiff",
        "CRS": crs_str,
        "BBOX": f"{bbox_buf[0]},{bbox_buf[1]},{bbox_buf[2]},{bbox_buf[3]}",
        "WIDTH": ancho_px,
        "HEIGHT": alto_px,
        "TRANSPARENT": "TRUE"
    }

    resp = session.get(wms_url, params=params, timeout=timeout)

    if resp.status_code != 200:
        raise ValueError(f"El servidor WMS respondió con código de estado HTTP {resp.status_code}")

    content_type = resp.headers.get("Content-Type", "").lower()
    start_bytes = resp.content[:600]

    # Detección de error devuelto en formato XML
    if (
        "xml" in content_type
        or start_bytes.startswith(b"<?xml")
        or b"<ServiceException" in start_bytes
        or b"<ExceptionReport" in start_bytes
    ):
        text = resp.text
        m = re.search(r"<ServiceException[^>]*>(.*?)</ServiceException>", text, re.DOTALL)
        if m:
            clean_err = m.group(1).strip()
            raise ValueError(f"Servidor WMS (IGN): {clean_err}")
        else:
            snippet = text[:300].replace("\n", " ").strip()
            raise ValueError(f"Excepción de servicio WMS: {snippet}")

    if "image" not in content_type:
        raise ValueError(f"Respuesta no es imagen (Content-Type: '{content_type}')")

    return resp.content


def fetch_xyz_ortho(
    session: requests.Session,
    tile_url_template: str,
    crs_str: str,
    bbox_buf: Tuple[float, float, float, float],
    ancho_px: int,
    alto_px: int,
    timeout: int = 25
) -> bytes:
    """
    Descarga ortofotografía satelital desde servidores de teselas XYZ estándar (Google Maps / Esri)
    en Web Mercator (EPSG:3857) y rectifica con precisión subpíxel al Bounding Box y resolución
    exactos del sistema de coordenadas local del dibujo (EPSG:25830, etc.), retornando un archivo TIFF.
    """
    ancho_px = min(4000, max(1, int(ancho_px)))
    alto_px = min(4000, max(1, int(alto_px)))

    t_3857 = Transformer.from_crs(crs_str, "EPSG:3857", always_xy=True)
    t_4326 = Transformer.from_crs(crs_str, "EPSG:4326", always_xy=True)

    minx, miny, maxx, maxy = bbox_buf
    target_res_x = (maxx - minx) / ancho_px
    target_res_y = (maxy - miny) / alto_px
    target_res = min(target_res_x, target_res_y)

    lon_c, lat_c = t_4326.transform((minx + maxx) / 2.0, (miny + maxy) / 2.0)
    cos_lat = max(0.05, math.cos(math.radians(lat_c)))

    # Resolución en el ecuador a Zoom 0 es 156543.03392 m/px
    if target_res > 0:
        raw_zoom = math.log2((156543.03392 * cos_lat) / target_res)
        zoom = round(raw_zoom)
    else:
        zoom = 18
    zoom = max(1, min(20, int(zoom)))

    # 4 esquinas del recuadro proyectado en UTM: UL, LL, LR, UR
    corners = [
        (minx, maxy),  # Upper-Left
        (minx, miny),  # Lower-Left
        (maxx, miny),  # Lower-Right
        (maxx, maxy)   # Upper-Right
    ]
    corners_3857 = [t_3857.transform(x, y) for x, y in corners]

    origin_shift = 20037508.342789244

    def get_pixel_coords(z_level: int):
        s_world = 256.0 * (2 ** z_level)
        px_list = []
        for x, y in corners_3857:
            px = (x + origin_shift) / (2.0 * origin_shift) * s_world
            py = (origin_shift - y) / (2.0 * origin_shift) * s_world
            px_list.append((px, py))
        return px_list

    px_corners = get_pixel_coords(zoom)
    min_px_x = min(p[0] for p in px_corners)
    max_px_x = max(p[0] for p in px_corners)
    min_px_y = min(p[1] for p in px_corners)
    max_px_y = max(p[1] for p in px_corners)

    tile_x_min = int(math.floor(min_px_x / 256.0))
    tile_x_max = int(math.floor(max_px_x / 256.0))
    tile_y_min = int(math.floor(min_px_y / 256.0))
    tile_y_max = int(math.floor(max_px_y / 256.0))

    # Control de seguridad: si son más de 64 teselas, retroceder nivel de zoom
    while (tile_x_max - tile_x_min + 1) * (tile_y_max - tile_y_min + 1) > 64 and zoom > 2:
        zoom -= 1
        px_corners = get_pixel_coords(zoom)
        min_px_x = min(p[0] for p in px_corners)
        max_px_x = max(p[0] for p in px_corners)
        min_px_y = min(p[1] for p in px_corners)
        max_px_y = max(p[1] for p in px_corners)
        tile_x_min = int(math.floor(min_px_x / 256.0))
        tile_x_max = int(math.floor(max_px_x / 256.0))
        tile_y_min = int(math.floor(min_px_y / 256.0))
        tile_y_max = int(math.floor(max_px_y / 256.0))

    canvas_w = max(256, (tile_x_max - tile_x_min + 1) * 256)
    canvas_h = max(256, (tile_y_max - tile_y_min + 1) * 256)
    canvas = Image.new("RGB", (canvas_w, canvas_h), (230, 230, 230))

    def fetch_single_tile(tx, ty):
        sub = "mt" + str((tx + ty) % 4)
        url = tile_url_template.format(x=tx, y=ty, z=zoom, s=sub)
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Accept": "image/webp,image/apng,image/*,*/*;q=0.8"
        }
        try:
            resp = session.get(url, headers=headers, timeout=timeout)
            if resp.status_code == 200 and len(resp.content) > 100:
                return tx, ty, resp.content
        except Exception:
            pass
        return tx, ty, None

    tile_coords = [(tx, ty) for ty in range(tile_y_min, tile_y_max + 1) for tx in range(tile_x_min, tile_x_max + 1)]
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(12, len(tile_coords) or 1)) as pool:
        futures = [pool.submit(fetch_single_tile, tx, ty) for tx, ty in tile_coords]
        for fut in concurrent.futures.as_completed(futures):
            tx, ty, data = fut.result()
            if data:
                try:
                    img = Image.open(io.BytesIO(data)).convert("RGB")
                    cx = (tx - tile_x_min) * 256
                    cy = (ty - tile_y_min) * 256
                    canvas.paste(img, (cx, cy))
                except Exception:
                    pass

    # Coordenadas relativas en el lienzo para las 4 esquinas: UL, LL, LR, UR
    quad_data = []
    for px, py in px_corners:
        quad_data.append(px - (tile_x_min * 256.0))
        quad_data.append(py - (tile_y_min * 256.0))

    rectified = canvas.transform(
        (ancho_px, alto_px),
        Image.QUAD,
        tuple(quad_data),
        resample=Image.BICUBIC
    )

    out_buf = io.BytesIO()
    rectified.save(out_buf, format="TIFF")
    return out_buf.getvalue()


# --------------------------------------------------------------------------------------
# 4. MAPA INTERACTIVO DE CONFIRMACIÓN DE UBICACIÓN
# --------------------------------------------------------------------------------------
def generate_preview_map(
    polygons: List[Dict[str, Any]],
    crs_str: str,
    buffer_pct: float = 0.04,
    active_service_key: str = "google_sat",
    custom_wms_url: str = "",
    custom_wms_layer: str = "",
    custom_wms_tag: str = "wms_custom"
) -> Optional[folium.Map]:
    """
    Reproyecta los vértices de los polígonos al sistema WGS 84 (EPSG:4326)
    y crea un mapa interactivo con ortofotografía satelital y capas oficiales del IGN
    (Ortofoto PNOA, Mapa Ráster MTN y Relieve MDT).
    Muestra el contorno de la geometría CAD (línea continua) y el polígono envolvente
    del encuadre exacto de la imagen de salida TIF resultante (línea discontinua con buffer).
    """
    if not polygons:
        return None

    try:
        transformer = Transformer.from_crs(crs_str, "EPSG:4326", always_xy=True)
    except Exception as e:
        st.warning(f"No se pudo inicializar la transformación desde {crs_str}: {e}")
        return None

    all_lats: List[float] = []
    all_lons: List[float] = []
    converted_polygons = []

    for p in polygons:
        pts = p.get("pts", [])
        bounds = p.get("bounds")
        if not pts or not bounds:
            continue

        latlon_ring = []
        for x, y in pts:
            try:
                lon, lat = transformer.transform(x, y)
                if -90 <= lat <= 90 and -180 <= lon <= 180:
                    latlon_ring.append([lat, lon])
                    all_lats.append(lat)
                    all_lons.append(lon)
            except Exception:
                continue

        # Marco rectangular ortogonal exacto de la salida TIF con buffer
        minx, miny, maxx, maxy = bounds
        dx = (maxx - minx) * buffer_pct
        dy = (maxy - miny) * buffer_pct
        bbox_buf = (minx - dx, miny - dy, maxx + dx, maxy + dy)
        width_salida = bbox_buf[2] - bbox_buf[0]
        height_salida = bbox_buf[3] - bbox_buf[1]
        bbox_corners = [
            (bbox_buf[0], bbox_buf[1]),
            (bbox_buf[2], bbox_buf[1]),
            (bbox_buf[2], bbox_buf[3]),
            (bbox_buf[0], bbox_buf[3])
        ]

        bbox_latlon = []
        for x, y in bbox_corners:
            try:
                lon, lat = transformer.transform(x, y)
                if -90 <= lat <= 90 and -180 <= lon <= 180:
                    bbox_latlon.append([lat, lon])
                    all_lats.append(lat)
                    all_lons.append(lon)
            except Exception:
                continue

        if len(latlon_ring) >= 3:
            converted_polygons.append({
                "info": p,
                "locations": latlon_ring,
                "bbox_locations": bbox_latlon,
                "width_salida": round(width_salida, 1),
                "height_salida": round(height_salida, 1),
                "center": [sum(pt[0] for pt in latlon_ring)/len(latlon_ring), sum(pt[1] for pt in latlon_ring)/len(latlon_ring)]
            })

    if not all_lats or not all_lons:
        return None

    center_lat = sum(all_lats) / len(all_lats)
    center_lon = sum(all_lons) / len(all_lons)
    min_lat, max_lat = min(all_lats), max(all_lats)
    min_lon, max_lon = min(all_lons), max(all_lons)

    m = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=15,
        control_scale=True
    )

    folium.TileLayer(
        tiles="https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}",
        attr="Google Maps",
        name="🌍 Google Satélite (Mundial)",
        overlay=False,
        control=True
    ).add_to(m)

    folium.TileLayer(
        tiles="https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}",
        attr="Google Maps",
        name="🌍 Google Híbrido (Satélite + Vías)",
        overlay=False,
        control=True
    ).add_to(m)

    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attr="Esri Satellite",
        name="🛰️ Esri World Imagery",
        overlay=False,
        control=True
    ).add_to(m)

    folium.TileLayer(
        tiles="OpenStreetMap",
        name="🗺️ Callejero OpenStreetMap",
        overlay=False,
        control=True
    ).add_to(m)

    folium.WmsTileLayer(
        url="https://www.ign.es/wms-inspire/pnoa-ma",
        layers="OI.OrthoimageCoverage",
        fmt="image/png",
        transparent=True,
        name="🇪🇸 Ortofoto PNOA WMS (IGN)",
        overlay=True,
        control=True,
        show=(active_service_key == "pnoa")
    ).add_to(m)

    folium.WmsTileLayer(
        url="https://www.ign.es/wms-inspire/mapa-raster",
        layers="mtn_rasterizado",
        fmt="image/png",
        transparent=True,
        name="🗺️ IGN Mapa Ráster MTN Topográfico",
        overlay=True,
        control=True,
        show=(active_service_key == "mapa_raster")
    ).add_to(m)

    folium.WmsTileLayer(
        url="https://servicios.idee.es/wms-inspire/mdt",
        layers="EL.GridCoverage",
        fmt="image/png",
        transparent=True,
        name="🏔️ IGN Modelo Digital Relieve (MDT)",
        overlay=True,
        control=True,
        show=(active_service_key == "mdt_relieve")
    ).add_to(m)

    if active_service_key == "custom" and custom_wms_url and custom_wms_layer:
        try:
            folium.WmsTileLayer(
                url=custom_wms_url,
                layers=custom_wms_layer,
                fmt="image/png",
                transparent=True,
                name=f"⚙️ WMS Personalizado ({custom_wms_tag})",
                overlay=True,
                control=True,
                show=True
            ).add_to(m)
        except Exception:
            pass

    colors = ["#f59e0b", "#06b6d4", "#10b981", "#ec4899", "#8b5cf6", "#3b82f6"]
    for i, poly_item in enumerate(converted_polygons):
        p_info = poly_item["info"]
        col = colors[i % len(colors)]

        # 1. Polígono del Marco de la Imagen de Salida (TIF resultante con buffer)
        if len(poly_item["bbox_locations"]) == 4:
            bbox_popup_html = f"""
            <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; font-size: 13px; line-height: 1.5; min-width: 210px; color: #f8fafc;">
                <div style="color: {col}; font-size: 14px; font-weight: 700; border-bottom: 1px solid #334155; padding-bottom: 4px; margin-bottom: 6px;">🖼️ Imagen de Salida TIF #{p_info['id']}</div>
                <div style="margin-bottom: 3px;"><b style="color: #94a3b8;">Archivo:</b> <span style="font-family: monospace;">{p_info['nombre_archivo']}.tif</span></div>
                <div style="margin-bottom: 3px;"><b style="color: #94a3b8;">Encuadre:</b> {poly_item['width_salida']} × {poly_item['height_salida']} m</div>
                <div style="margin-bottom: 3px;"><b style="color: #94a3b8;">Buffer perimetral:</b> {round(buffer_pct * 100)}%</div>
                <div><b style="color: #94a3b8;">Calidad recomendada:</b> <span style="color: #10b981; font-weight: 600;">{p_info.get('calidad_sugerida', '1.00 m/px')}</span></div>
            </div>
            """

            folium.Polygon(
                locations=poly_item["bbox_locations"],
                color=col,
                weight=2,
                dash_array="6, 6",
                fill=True,
                fill_color=col,
                fill_opacity=0.10,
                popup=folium.Popup(bbox_popup_html, max_width=320),
                tooltip=f"🖼️ Salida #{p_info['id']} | {poly_item['width_salida']}m × {poly_item['height_salida']}m"
            ).add_to(m)

        # 2. Polígono de la Geometría CAD (Parcela interior)
        popup_html = f"""
        <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; font-size: 13px; line-height: 1.5; min-width: 190px; color: #f8fafc;">
            <div style="color: {col}; font-size: 14px; font-weight: 700; border-bottom: 1px solid #334155; padding-bottom: 4px; margin-bottom: 6px;">📐 Geometría CAD #{p_info['id']}</div>
            <div style="margin-bottom: 3px;"><b style="color: #94a3b8;">Capa CAD:</b> <span style="background: #334155; padding: 1px 5px; border-radius: 4px; font-family: monospace;">{p_info['capa']}</span></div>
            <div style="margin-bottom: 3px;"><b style="color: #94a3b8;">Nombre:</b> {p_info['nombre_archivo']}</div>
            <div style="margin-bottom: 3px;"><b style="color: #94a3b8;">Dimensiones:</b> {p_info['ancho_m']} × {p_info['alto_m']} m</div>
            <div style="margin-bottom: 3px;"><b style="color: #94a3b8;">Área:</b> <span style="color: #38bdf8; font-weight: 600;">{p_info['area_m2']:,} m²</span> ({(p_info['area_m2']/10000):.2f} ha)</div>
            <div><b style="color: #94a3b8;">Calidad sugerida:</b> <span style="color: #10b981; font-weight: 600;">{p_info.get('calidad_sugerida', '1.00 m/px')}</span></div>
        </div>
        """

        folium.Polygon(
            locations=poly_item["locations"],
            color=col,
            weight=3,
            fill=True,
            fill_color=col,
            fill_opacity=0.35,
            popup=folium.Popup(popup_html, max_width=300),
            tooltip=f"📐 Minuta CAD #{p_info['id']} | {p_info['capa']} ({p_info['ancho_m']}m × {p_info['alto_m']}m)"
        ).add_to(m)

        folium.CircleMarker(
            location=poly_item["center"],
            radius=6,
            color="#ffffff",
            weight=2,
            fill=True,
            fill_color=col,
            fill_opacity=0.9,
            tooltip=f"Centroide Polígono #{p_info['id']}"
        ).add_to(m)

    m.fit_bounds([[min_lat, min_lon], [max_lat, max_lon]])
    folium.LayerControl(position="topright", collapsed=False).add_to(m)

    return m


# --------------------------------------------------------------------------------------
# 5. INTERFAZ GRÁFICA STREAMLIT
# --------------------------------------------------------------------------------------
def render_ui():
    """Construye y gestiona la interfaz interactiva de Streamlit."""

    st.markdown("""
    <style>
        /* Encabezado principal en Modo Oscuro */
        .main-header {
            background: linear-gradient(135deg, #091e3a 0%, #0f172a 50%, #1e293b 100%);
            border: 1px solid #334155;
            padding: 1.8rem 2rem;
            border-radius: 14px;
            color: #ffffff;
            margin-bottom: 1.5rem;
            box-shadow: 0 8px 24px rgba(0, 0, 0, 0.4);
        }
        .main-header h1 {
            color: #38bdf8 !important;
            margin: 0;
            font-size: 2.1rem;
            font-weight: 700;
            letter-spacing: -0.02em;
        }
        .main-header p {
            color: #cbd5e1 !important;
            margin: 0.5rem 0 0 0;
            font-size: 1.05rem;
        }

        /* Botón de descarga principal */
        .stDownloadButton button {
            background: linear-gradient(135deg, #10b981 0%, #059669 100%) !important;
            color: white !important;
            font-weight: bold !important;
            font-size: 1.05rem !important;
            padding: 0.75rem 2rem !important;
            border-radius: 10px !important;
            border: none !important;
            box-shadow: 0 4px 14px rgba(16, 185, 129, 0.35) !important;
            transition: all 0.2s ease !important;
        }
        .stDownloadButton button:hover {
            background: linear-gradient(135deg, #34d399 0%, #047857 100%) !important;
            transform: translateY(-2px);
            box-shadow: 0 6px 20px rgba(16, 185, 129, 0.45) !important;
        }

        /* Ajustes de contenedores y desplegables */
        div[data-testid="stExpander"] {
            border: 1px solid #334155 !important;
            background-color: #1e293b !important;
            border-radius: 10px !important;
        }
        div[data-testid="stExpander"] details summary {
            color: #f1f5f9 !important;
        }

        /* Métricas */
        div[data-testid="stMetricValue"] {
            color: #38bdf8 !important;
        }

        /* Leaflet Popups oscuros */
        .leaflet-popup-content-wrapper, .leaflet-popup-tip {
            background: #1e293b !important;
            color: #f8fafc !important;
            box-shadow: 0 10px 25px rgba(0,0,0,0.6) !important;
            border: 1px solid #334155 !important;
        }
        .leaflet-container {
            border-radius: 12px;
            border: 1px solid #334155;
        }
    </style>
    """, unsafe_allow_html=True)

    # ----------------------------------------------------------------------------------
    # BARRA LATERAL (SIDEBAR): CONFIGURACIÓN GLOBAL
    # ----------------------------------------------------------------------------------
    st.sidebar.header("⚙️ Configuración Global")

    # 1. Sistema de Referencia de Coordenadas (CRS / Proyección)
    st.sidebar.subheader("1. Proyección Cartográfica (CRS)")
    
    crs_mode = st.sidebar.radio(
        "Modo de selección del CRS:",
        options=["Código EPSG directo (Cualquier país)", "Preajustes regionales comunes"],
        index=0,
        horizontal=True,
        help="Introduce directamente el código EPSG de tu plano (ej: Australia 7855, España 25830, Colombia 9377) o usa un preajuste."
    )

    regional_presets = {
        "🇦🇺 Australia - GDA2020 / MGA zone 55 (EPSG:7855)": 7855,
        "🇦🇺 Australia - GDA2020 / MGA zone 56 (EPSG:7856)": 7856,
        "🇦🇺 Australia - GDA2020 / MGA zone 54 (EPSG:7854)": 7854,
        "🇦🇺 Australia - GDA94 / MGA zone 55 (EPSG:28355)": 28355,
        "🇦🇺 Australia - GDA94 / MGA zone 56 (EPSG:28356)": 28356,
        "🇪🇸 España - ETRS89 / UTM 30N (EPSG:25830)": 25830,
        "🇪🇸 España - ETRS89 / UTM 29N (Galicia) (EPSG:25829)": 25829,
        "🇪🇸 España - ETRS89 / UTM 31N (Cataluña/Baleares) (EPSG:25831)": 25831,
        "🇪🇸 Canarias - WGS 84 / UTM 28N (EPSG:32628)": 32628,
        "🌎 Global - WGS 84 / UTM 30N (EPSG:32630)": 32630,
        "🌎 Global - WGS 84 / Web Mercator (EPSG:3857)": 3857,
        "🌎 Global - WGS 84 Geográficas (EPSG:4326)": 4326,
        "🇲🇽 México - ITRF2008 / UTM 14N (EPSG:6369)": 6369,
        "🇨🇴 Colombia - MAGNA-SIRGAS Origen Nacional (EPSG:9377)": 9377,
        "🇨🇱 Chile - SIRGAS-Chile / UTM 19S (EPSG:5361)": 5361,
        "🇦🇷 Argentina - POSGAR 07 / Faja 4 (EPSG:5346)": 5346,
        "🇺🇸 USA - NAD83 / UTM zone 18N (EPSG:26918)": 26918,
        "🇺🇸 USA - NAD83 / UTM zone 10N (EPSG:26910)": 26910
    }

    if crs_mode == "Código EPSG directo (Cualquier país)":
        epsg_raw = st.sidebar.text_input(
            "Código EPSG de tu plano CAD:",
            value="25830",
            help="Ejemplos mundiales: 7855 o 28355 (Australia), 25830 (España), 32618 (Colombia/Panamá/USA), 32719 (Chile/Perú), 32630 (Europa/África), 6369 (México)."
        ).strip().upper().replace("EPSG:", "").strip()

        try:
            epsg_code = int(epsg_raw)
        except ValueError:
            epsg_code = 25830
            st.sidebar.warning("⚠️ Código numérico no válido. Usando EPSG:25830 por defecto.")
    else:
        preset_label = st.sidebar.selectbox(
            "Selecciona proyección regional:",
            options=list(regional_presets.keys()),
            index=0
        )
        epsg_code = regional_presets[preset_label]

    crs_str = f"EPSG:{epsg_code}"

    try:
        pyproj_crs = CRS.from_epsg(epsg_code)
        crs_name = pyproj_crs.name
        area_name = pyproj_crs.area_of_use.name if pyproj_crs.area_of_use else "Global / No especificado"
        st.sidebar.markdown(f"""
        <div style="background: rgba(16, 185, 129, 0.12); border: 1px solid #059669; border-radius: 8px; padding: 8px 12px; margin-top: 5px; margin-bottom: 10px;">
            <div style="font-weight: 700; color: #10b981; font-size: 13px;">✅ EPSG:{epsg_code} Activo</div>
            <div style="color: #f1f5f9; font-size: 12px; font-weight: 600;">{crs_name}</div>
            <div style="color: #94a3b8; font-size: 11px; margin-top: 2px;">📍 Ámbito: {area_name[:55]}...</div>
        </div>
        """, unsafe_allow_html=True)
    except Exception as crs_err:
        st.sidebar.error(f"⚠️ EPSG:{epsg_code} no reconocido: {crs_err}")

    # 2. Buffer porcentual de encuadre
    st.sidebar.subheader("2. Margen de Encuadre (Buffer)")
    buffer_slider = st.sidebar.slider(
        "Buffer porcentual (%):",
        min_value=0,
        max_value=15,
        value=4,
        step=1,
        help="Margen perimetral adicional (%) alrededor del polígono para no cortar bordes de obra o parcela."
    )
    buffer_pct = buffer_slider / 100.0

    # 3. Estrategia para áreas extensas (> 4000 px)
    st.sidebar.subheader("3. Estrategia para Áreas Extensas")
    large_area_mode = st.sidebar.radio(
        "Si la imagen excede el límite del IGN (4000 px):",
        options=[
            "Ajustar a 4000 px (Imagen única)",
            "Dividir en mosaico / teselas (Máxima resolución)"
        ],
        index=0,
        help=(
            "El servidor del IGN rechaza peticiones mayores a 4096 px. "
            "'Ajustar a 4000 px' escala suavemente para mantener un único archivo .tif. "
            "'Dividir en mosaico' crea teselas contiguas respetando la resolución milimétrica exacta."
        )
    )

    # 4. Servicio Cartográfico y Satelital (WMS IGN / Google Satélite / Esri)
    st.sidebar.subheader("4. Servicio Cartográfico / Satelital")
    service_keys = list(SERVICES_CATALOG.keys())
    service_labels = [SERVICES_CATALOG[k]["name"] for k in service_keys]

    selected_service_label = st.sidebar.selectbox(
        "Capa o servicio a descargar:",
        options=service_labels,
        index=0,
        help=(
            "Selecciona la fuente de imagen para tu plano CAD:\n"
            "- Ortofoto Aérea PNOA (IGN España - Vuelo oficial de máxima resolución)\n"
            "- Google Satélite (Fotografía satelital mundial de alta resolución)\n"
            "- Google Híbrido (Satélite con carreteras, autopistas y nombres)\n"
            "- Esri World Imagery (Imágenes satelitales globales de alta resolución)\n"
            "- Mapa Ráster IGN (Cartografía MTN25/MTN50 oficial con curvas de nivel)\n"
            "- Modelo Digital del Terreno (Sombreado continuo de relieve LiDAR/MDT)\n"
            "- Personalizado (Cualquier servidor WMS 1.3.0)"
        )
    )

    selected_service_key = service_keys[service_labels.index(selected_service_label)]
    service_info = SERVICES_CATALOG[selected_service_key]

    if selected_service_key == "custom":
        st.sidebar.markdown("""
        <div style="background: rgba(56, 189, 248, 0.1); border-left: 3px solid #38bdf8; padding: 6px 10px; border-radius: 4px; margin-bottom: 8px; font-size: 12px; color: #cbd5e1;">
            💡 <b>Conexión WMS Universal:</b> Puedes conectar cualquier servidor de cartografía u ortofotos oficial del mundo (Australia, Europa, América, etc.).
        </div>
        """, unsafe_allow_html=True)
        wms_url = st.sidebar.text_input("URL base del servicio WMS:", value=service_info.get("url", ""), placeholder="https://ejemplo.gov/wms", help="URL base del servicio OGC WMS")
        wms_layer = st.sidebar.text_input("Nombre técnico de la capa (Layer):", value=service_info.get("layer", ""), placeholder="imagery_layer", help="Identificador exacto de la capa en el servidor WMS")
        wms_tag = st.sidebar.text_input("Etiqueta para archivos (Tag):", value="wms_custom", help="Prefijo corto que se incluirá en los nombres de archivo .tif y .tfw")
    else:
        st.sidebar.caption(f"ℹ️ **{service_info['badge']}:** {service_info['description']}")
        with st.sidebar.expander("⚙️ Ver detalles técnicos del servicio", expanded=False):
            if service_info.get("type") == "xyz":
                info_tech = f"Tipo: Servidor de teselas XYZ (Web Mercator EPSG:3857)\nURL Plantilla: {service_info['url']}"
            else:
                info_tech = f"Tipo: OGC WMS 1.3.0\nURL: {service_info['url']}\nCapa: {service_info['layer']}"
                if selected_service_key == "mapa_raster":
                    info_tech += "\nEndpoint WMTS: https://www.ign.es/wmts/mapa-raster"
            st.code(info_tech, language="text")
        wms_url = service_info["url"]
        wms_layer = service_info.get("layer", "")
        wms_tag = service_info["tag"]

    # 5. Límites de seguridad
    with st.sidebar.expander("🛡️ Límites de Seguridad de Descarga", expanded=False):
        max_pixels_lado = st.number_input(
            "Máx. píxeles por lado:",
            min_value=1000,
            max_value=4000,
            value=4000,
            step=250,
            help="Límite del servidor IGN: Máximo 4000 px para evitar rechazos por MapServer (MAXSIZE=4096)."
        )
        max_pixels_totales = st.number_input(
            "Máx. píxeles acumulados:",
            min_value=1000000,
            max_value=16000000,
            value=16000000,
            step=1000000,
            help="Límite acumulado de resolución (ancho × alto) de seguridad."
        )

    # ----------------------------------------------------------------------------------
    # ENCABEZADO Y EXPLICACIÓN PARA USUARIOS DE AUTOCAD
    # ----------------------------------------------------------------------------------
    st.markdown("""
    <div class="main-header">
        <h1>🌍 GeoRaster to CAD | Extractor Georreferenciado Universal</h1>
        <p>Extracción y georreferenciación de <b>cualquier servidor WMS del mundo</b>, Google Satélite, Esri y cartografía oficial para AutoCAD, Civil 3D y BricsCAD en formato <b>TIF + TFW</b>.</p>
    </div>
    """, unsafe_allow_html=True)

    with st.expander("📖 Guía de uso rápido y cómo insertar en AutoCAD / Civil 3D", expanded=False):
        st.markdown("""
        **Instrucciones para delineantes, topógrafos e ingenieros de cualquier país:**
        1. **Define la proyección (CRS)**: En la barra lateral, escribe directamente el código **EPSG** de tu plano (ej. `7855` para Australia GDA2020, `25830` para España ETRS89, `9377` para Colombia MAGNA, `32618` para WGS84 UTM 18N, etc.) o elige un preajuste regional.
        2. **Selecciona la fuente de imagen**: Elige **Google Satélite** (mundial limpio), **Google Híbrido** (con vías y nombres), **Esri World Imagery**, **Cualquier servidor WMS del mundo** o servicios nacionales (PNOA/IGN).
        3. **Carga tu archivo `.dxf`**: El dibujo debe contener polilíneas cerradas (`LWPOLYLINE` o `POLYLINE`) que delimiten el ámbito de trabajo o parcelas.
        4. **Verifica la ubicación en el visor interactivo**: Confirma visualmente que las geometrías caen sobre la imagen en la posición real de tu proyecto y revisa el recuadro de salida.
        5. **Descarga el `.zip`**: Contiene los archivos georreferenciados para cada polígono:
           - **`.tif`**: Imagen ráster recortada en máxima resolución.
           - **`.tfw`**: Archivo *World File* de calibración espacial con coordenadas UTM/proyectadas exactas.
        
        **Cómo insertar en AutoCAD en su posición proyectada exacta:**
        - **AutoCAD Map 3D / Civil 3D**: Ejecuta el comando `_MAPIINSERT` (o ve a *Insertar* -> *Imagen ráster*). Al seleccionar los archivos `.tif`, AutoCAD detectará automáticamente los archivos `.tfw` asociados e insertará las ortofotos en sus **coordenadas reales de proyecto**.
        - **AutoCAD Estándar / LT**: Inserta mediante el comando `_IMAGEATTACH` (`ENLAZARIMG`).
        - **Consejo para minutas o parcelas en diagonal**: Para recortar la ortofoto siguiendo la forma exacta de una minuta inclinada en AutoCAD, usa el comando nativo `_IMAGECLIP` (`DELIMIMG`) -> *Nuevo contorno* (`N`) -> *Seleccionar polilínea* (`S`) y toca tu polilínea. AutoCAD ocultará los bordes sobrantes al instante manteniendo la georreferenciación perfecta.
        """)

    if "processed_zip_data" not in st.session_state:
        st.session_state["processed_zip_data"] = None
    if "processed_zip_name" not in st.session_state:
        st.session_state["processed_zip_name"] = None
    if "processed_summary" not in st.session_state:
        st.session_state["processed_summary"] = []
    if "demo_active" not in st.session_state:
        st.session_state["demo_active"] = False

    # ----------------------------------------------------------------------------------
    # CARGA DE ARCHIVO DXF Y MODO DE PRUEBA
    # ----------------------------------------------------------------------------------
    col_up, col_demo = st.columns([3, 1])

    with col_up:
        uploaded_file = st.file_uploader(
            "📁 Carga tu plano AutoCAD en formato DXF (.dxf):",
            type=["dxf"],
            help="Sube un archivo DXF que contenga una o más polilíneas cerradas."
        )

    with col_demo:
        st.write("")
        st.write("")
        btn_demo = st.button("🧪 Probar con DXF de ejemplo", help="Genera un plano DXF con parcelas en Madrid (EPSG:25830), incluyendo una minuta en diagonal")
        if btn_demo:
            st.session_state["demo_active"] = True
            st.session_state["processed_zip_data"] = None

    dxf_bytes = None
    dxf_display_name = ""

    if uploaded_file is not None:
        st.session_state["demo_active"] = False
        dxf_bytes = uploaded_file.getvalue()
        dxf_display_name = uploaded_file.name
    elif st.session_state.get("demo_active", False):
        demo_doc = ezdxf.new("R2010")
        demo_msp = demo_doc.modelspace()
        
        # Parcela 1: Solar urbano en Madrid (Área pequeña < 0.5 ha -> 0.25 m/px Muy Alta)
        p1 = [(441300, 4478100), (441360, 4478100), (441360, 4478150), (441300, 4478150)]
        poly1 = demo_msp.add_lwpolyline(p1, close=True)
        poly1.dxf.layer = "SOLAR_EDIFICACION"
        
        # Parcela 2: Parcela industrial / nave en Madrid (1.2 ha -> 0.50 m/px Alta)
        p2 = [(441800, 4473800), (441920, 4473800), (441920, 4473900), (441800, 4473900)]
        poly2 = demo_msp.add_lwpolyline(p2, close=True)
        poly2.dxf.layer = "PARCELA_INDUSTRIAL"

        # Parcela 3: Ámbito de obra / desarrollo en Madrid (6.0 ha -> 1.00 m/px Estándar)
        p3 = [(441300, 4476800), (441600, 4476980), (441480, 4477180), (441180, 4477000)]
        poly3 = demo_msp.add_lwpolyline(p3, close=True)
        poly3.dxf.layer = "AMBITO_OBRA"

        out_str = io.StringIO()
        demo_doc.write(out_str)
        dxf_bytes = out_str.getvalue().encode("utf-8")
        dxf_display_name = "demo_madrid_pnoa.dxf"
        st.info("💡 Modo de demostración activo: Plano con 3 geometrías en Madrid (EPSG:25830).")

    # ----------------------------------------------------------------------------------
    # EXTRACCIÓN Y VISOR CARTOGRÁFICO DE CONFIRMACIÓN
    # ----------------------------------------------------------------------------------
    if dxf_bytes is not None:
        try:
            with st.spinner("Leyendo entidades del plano DXF..."):
                extracted_polygons = parse_dxf_polygons(dxf_bytes, dxf_display_name, service_tag=wms_tag)

            if not extracted_polygons:
                st.warning("""
                ⚠️ **No se encontraron polilíneas cerradas en el espacio modelo del archivo DXF.**
                
                **Recomendaciones para AutoCAD:**
                - Comprueba que las parcelas son entidades `LWPOLYLINE` o `POLYLINE`.
                - Selecciona la polilínea, abre la paleta de Propiedades (`Ctrl+1`) y verifica que **Cerrada = Sí**.
                - En la línea de comandos, ejecuta `EDITPOL` (`PEDIT`) y elige la opción **Cerrar**.
                """)
            else:
                col_m1, col_m2, col_m3, col_m4 = st.columns(4)
                layers_found = list(set(p["capa"] for p in extracted_polygons))
                col_m1.metric("Polilíneas detectadas", len(extracted_polygons))
                col_m2.metric("Capas CAD", len(layers_found))
                col_m3.metric("Proyección", crs_str)
                col_m4.metric("Servicio activo", service_info["badge"])

                # Inicializar y sincronizar el estado de la tabla antes de renderizar el mapa
                state_key = f"df_{dxf_display_name}_{len(extracted_polygons)}_{wms_tag}"
                if state_key not in st.session_state:
                    table_data = []
                    for p in extracted_polygons:
                        row_copy = dict(p)
                        row_copy.pop("pts", None)
                        table_data.append(row_copy)
                    st.session_state[state_key] = pd.DataFrame(table_data)

                active_df = st.session_state[state_key]

                # VISOR CARTOGRÁFICO INTERACTIVO PARA CONFIRMAR UBICACIÓN
                st.markdown("---")
                st.markdown(f"### 🗺️ Confirmación Visual de Ubicación y Encuadre ({service_info['badge']})")
                st.caption(
                    "Verifica en el visor interactivo la ubicación de tus geometrías CAD (**contorno sólido**) "
                    "y el **recuadro de la imagen de salida TIF** que se descargará (**línea discontinua** con el margen de buffer aplicado). "
                    "Puedes activar/desactivar las capas de Ortofoto PNOA, Mapa Ráster MTN o Relieve en el selector superior derecho."
                )

                preview_map = generate_preview_map(
                    extracted_polygons,
                    crs_str,
                    buffer_pct=buffer_pct,
                    active_service_key=selected_service_key,
                    custom_wms_url=wms_url if selected_service_key == "custom" else "",
                    custom_wms_layer=wms_layer if selected_service_key == "custom" else "",
                    custom_wms_tag=wms_tag if selected_service_key == "custom" else "custom"
                )
                if preview_map is not None:
                    st_folium(preview_map, use_container_width=True, height=470, returned_objects=[])
                else:
                    st.info("ℹ️ No fue posible proyectar las geometrías sobre el mapa. Comprueba que el CRS coincida con las coordenadas del plano.")

                # TABLA DE PERSONALIZACIÓN Y RESOLUCIÓN
                st.markdown("---")
                st.markdown("### 📋 Personalización de Polígonos y Recomendación de Calidad")

                with st.expander("💡 Guía de Calidad Recomendada de Imagen según el Tamaño del Área", expanded=False):
                    st.markdown("""
                    La aplicación analiza el área ($m^2$ y hectáreas) de cada polígono CAD y asigna automáticamente la resolución óptima recomendada para obtener el máximo nivel de detalle sin sobrecargar la memoria ni exceder los límites de descarga del IGN:
                    
                    | Superficie de la Geometría | Nivel de Calidad | Resolución Sugerida ($m/px$) | Tipo de Proyecto / Uso Habitual |
                    | :--- | :--- | :--- | :--- |
                    | **< 5.000 m²** (< 0.5 ha) | 🌟 **Muy Alta** | `0.25 m/px` | Solares urbanos, parcelas pequeñas, edificación y detalle fino |
                    | **5.000 a 25.000 m²** (0.5 a 2.5 ha) | 🔍 **Alta** | `0.50 m/px` | Parcelas y naves industriales, urbanizaciones compactas |
                    | **25.000 a 150.000 m²** (2.5 a 15 ha) | 📐 **Estándar** | `1.00 m/px` | Obras lineales medianas, polígonos, desarrollos urbanísticos |
                    | **150.000 a 1.000.000 m²** (15 a 100 ha) | 🚜 **Normal** | `2.00 m/px` | Grandes fincas rústicas, parques solares, infraestructuras |
                    | **> 1.000.000 m²** (> 100 ha) | 🗺️ **Panorámica** | `4.00 m/px` | Escala territorial, términos municipales, cuencas |
                    
                    *Nota: Cada fila ha sido inicializada automáticamente con la resolución recomendada. Puedes ajustar los valores a tu gusto de manera individual o por lotes.*
                    """)

                q1, q2, q3, q4 = st.columns([2.0, 1.2, 1.4, 1.4])
                with q1:
                    preset_res = st.selectbox(
                        "Resolución rápida sugerida:",
                        options=[
                            "Mantener selección individual",
                            "🪄 Recomendada según área (Auto)",
                            "0.25 m/px - Muy Alta (< 0.5 ha)",
                            "0.50 m/px - Alta (0.5 a 2.5 ha)",
                            "1.00 m/px - Estándar (2.5 a 15 ha)",
                            "2.00 m/px - Normal (15 a 100 ha)",
                            "4.00 m/px - Panorámica (> 100 ha)"
                        ],
                        index=0
                    )

                with q2:
                    st.write("")
                    st.write("")
                    btn_apply_all = st.button("Aplicar a todos", use_container_width=True)

                with q3:
                    st.write("")
                    st.write("")
                    btn_apply_rec = st.button("🪄 Calidad sugerida", use_container_width=True, help="Restaura la resolución recomendada según el área en m² de cada polígono")

                with q4:
                    st.write("")
                    st.write("")
                    btn_invert_sel = st.button("Alternar selección", use_container_width=True)

                if btn_apply_rec:
                    for idx, row in active_df.iterrows():
                        rec_res, rec_label, _ = get_recommended_resolution(float(row.get("area_m2", 0)))
                        active_df.at[idx, "resolucion_m_px"] = rec_res
                        active_df.at[idx, "calidad_sugerida"] = rec_label
                    st.session_state[state_key] = active_df
                    st.rerun()

                if btn_apply_all and preset_res != "Mantener selección individual":
                    if "Recomendada" in preset_res:
                        for idx, row in active_df.iterrows():
                            rec_res, rec_label, _ = get_recommended_resolution(float(row.get("area_m2", 0)))
                            active_df.at[idx, "resolucion_m_px"] = rec_res
                            active_df.at[idx, "calidad_sugerida"] = rec_label
                    else:
                        val = float(preset_res.split(" ")[0])
                        active_df["resolucion_m_px"] = val
                    st.session_state[state_key] = active_df
                    st.rerun()

                if btn_invert_sel:
                    active_df["incluir"] = not active_df["incluir"].all()
                    st.session_state[state_key] = active_df
                    st.rerun()

                column_config = {
                    "incluir": st.column_config.CheckboxColumn(
                        "Descargar",
                        help="Marcar para incluir en la descarga",
                        default=True
                    ),
                    "id": st.column_config.NumberColumn("ID", disabled=True, width="small"),
                    "capa": st.column_config.TextColumn("Capa CAD", disabled=True, width="medium"),
                    "area_m2": st.column_config.NumberColumn(
                        "Área (m²)",
                        disabled=True,
                        format="%.1f m²",
                        help="Superficie total encerrada por la polilínea CAD"
                    ),
                    "calidad_sugerida": st.column_config.TextColumn(
                        "Calidad Sugerida",
                        help="Resolución recomendada por el sistema según el área de la geometría",
                        disabled=True,
                        width="medium"
                    ),
                    "resolucion_m_px": st.column_config.NumberColumn(
                        "Resolución (m/px)",
                        help="Tamaño de píxel en metros (Personalizable: Muy Alta 0.25, Alta 0.50, Estándar 1.00, Normal 2.00, Panorámica 4.00 o manual)",
                        min_value=0.1,
                        max_value=20.0,
                        step=0.25,
                        format="%.2f m/px",
                        required=True,
                        width="medium"
                    ),
                    "nombre_archivo": st.column_config.TextColumn(
                        "Nombre Base Archivo",
                        help="Nombre que recibirán los archivos .tif y .tfw",
                        required=True,
                        width="large"
                    ),
                    "ancho_m": st.column_config.NumberColumn("Ancho (m)", disabled=True, format="%.1f m"),
                    "alto_m": st.column_config.NumberColumn("Alto (m)", disabled=True, format="%.1f m"),
                    "num_vertices": st.column_config.NumberColumn("Vértices", disabled=True),
                    "bounds": None
                }

                column_order = [
                    "incluir", "id", "capa",
                    "area_m2", "calidad_sugerida", "resolucion_m_px",
                    "nombre_archivo", "ancho_m", "alto_m", "num_vertices"
                ]

                edited_df = st.data_editor(
                    active_df,
                    column_config=column_config,
                    column_order=column_order,
                    hide_index=True,
                    use_container_width=True,
                    num_rows="fixed",
                    key=f"editor_{state_key}"
                )
                st.session_state[state_key] = edited_df

                selected_rows = edited_df[edited_df["incluir"] == True].to_dict("records")
                st.info(f"📍 **{len(selected_rows)}** polígono(s) seleccionado(s) para descarga.")

                # ------------------------------------------------------------------------------
                # BOTÓN DE DESCARGA WMS
                # ------------------------------------------------------------------------------
                st.write("")
                btn_process = st.button(
                    f"🚀 Descargar Cartografía ({service_info['badge']}) y Generar Georreferenciación",
                    type="primary",
                    use_container_width=True,
                    disabled=(len(selected_rows) == 0)
                )

                if btn_process:
                    st.session_state["processed_zip_data"] = None
                    st.session_state["processed_summary"] = []

                    progress_bar = st.progress(0.0)
                    status_text = st.empty()
                    log_expander = st.expander("📝 Detalle del procesamiento en tiempo real", expanded=True)

                    session = create_resilient_session(timeout=35)
                    zip_buffer = io.BytesIO()

                    success_count = 0
                    summary_log = []
                    used_names = set()
                    total_count = len(selected_rows)

                    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
                        for idx, row in enumerate(selected_rows):
                            progress_bar.progress(idx / total_count)

                            clean_base = sanitize_filename(row["nombre_archivo"])
                            pixel_size = float(row["resolucion_m_px"])
                            bounds = row["bounds"]

                            # Determinar tareas de descarga (única o teselas)
                            if "mosaico" in large_area_mode.lower():
                                tile_jobs = compute_tiled_georeferencing(
                                    bounds=bounds,
                                    buffer_pct=buffer_pct,
                                    pixel_size=pixel_size,
                                    max_tile_side=4000
                                )
                            else:
                                single_job = compute_georeferencing_parameters(
                                    bounds=bounds,
                                    buffer_pct=buffer_pct,
                                    pixel_size=pixel_size,
                                    max_pixels_lado=max_pixels_lado,
                                    max_pixels_totales=max_pixels_totales
                                )
                                tile_jobs = [single_job]

                            for job in tile_jobs:
                                suffix = job.get("tile_suffix", "")
                                final_name = f"{clean_base}{suffix}"
                                
                                counter = 1
                                while final_name in used_names:
                                    final_name = f"{clean_base}{suffix}_{counter}"
                                    counter += 1
                                used_names.add(final_name)

                                status_text.markdown(
                                    f"⏳ **Descargando [{idx + 1}/{total_count}] ({service_info['badge']}):** `{final_name}.tif` "
                                    f"({job['ancho_px']} × {job['alto_px']} px, res: {abs(job['pixel_x']):.2f} m/px)..."
                                )

                                try:
                                    if service_info.get("type") == "xyz":
                                        img_bytes = fetch_xyz_ortho(
                                            session=session,
                                            tile_url_template=service_info["url"],
                                            crs_str=crs_str,
                                            bbox_buf=job["bbox_buf"],
                                            ancho_px=job["ancho_px"],
                                            alto_px=job["alto_px"]
                                        )
                                    else:
                                        img_bytes = fetch_wms_ortho(
                                            session=session,
                                            wms_url=wms_url,
                                            wms_layer=wms_layer,
                                            crs_str=crs_str,
                                            bbox_buf=job["bbox_buf"],
                                            ancho_px=job["ancho_px"],
                                            alto_px=job["alto_px"]
                                        )

                                    zf.writestr(f"{final_name}.tif", img_bytes)
                                    zf.writestr(f"{final_name}.tfw", job["tfw_content"].encode("utf-8"))

                                    size_kb = len(img_bytes) / 1024.0
                                    scaled_note = " (ajustado al límite del IGN)" if job.get("scaled", False) else ""
                                    log_expander.success(
                                        f"✅ [{final_name}] Descargado ({job['ancho_px']} × {job['alto_px']} px, "
                                        f"{size_kb:.1f} KB, res: {abs(job['pixel_x']):.3f} m/px){scaled_note}"
                                    )

                                    summary_log.append({
                                        "Archivo": final_name,
                                        "Servicio": service_info["badge"],
                                        "Dimensiones (px)": f"{job['ancho_px']} × {job['alto_px']}",
                                        "Extensión (m)": f"{job['width_m']:.1f} × {job['height_m']:.1f}",
                                        "Resolución Real": f"{abs(job['pixel_x']):.3f} m/px",
                                        "Estado": "Descargado",
                                        "Detalle": f"{size_kb:.1f} KB"
                                    })
                                    success_count += 1

                                except Exception as err:
                                    err_msg = str(err)
                                    log_expander.error(f"❌ [{final_name}] Error: {err_msg}")
                                    summary_log.append({
                                        "Archivo": final_name,
                                        "Servicio": service_info["badge"],
                                        "Dimensiones (px)": f"{job['ancho_px']} × {job['alto_px']}",
                                        "Extensión (m)": f"{job['width_m']:.1f} × {job['height_m']:.1f}",
                                        "Resolución Real": "-",
                                        "Estado": "Error",
                                        "Detalle": err_msg
                                    })

                    progress_bar.progress(1.0)
                    status_text.empty()

                    if success_count > 0:
                        zip_buffer.seek(0)
                        st.session_state["processed_zip_data"] = zip_buffer.getvalue()
                        base_dxf_stem = os.path.splitext(sanitize_filename(dxf_display_name))[0]
                        st.session_state["processed_zip_name"] = f"cartografia_{wms_tag}_{base_dxf_stem}.zip"
                        st.session_state["processed_summary"] = summary_log
                        st.balloons()
                    else:
                        st.error("No se pudo descargar ninguna imagen cartográfica. Verifica la conectividad con el servicio WMS y las coordenadas.")

        except Exception as e:
            st.error(f"❌ Error al procesar el archivo DXF: {e}")
            with st.expander("Detalle del error técnico"):
                st.code(traceback.format_exc())

    # ----------------------------------------------------------------------------------
    # ENTREGA DE RESULTADOS: BOTÓN DE DESCARGA FINAL
    # ----------------------------------------------------------------------------------
    if st.session_state.get("processed_zip_data") is not None:
        st.markdown("---")
        st.markdown("### 📦 Descarga de Resultados")

        c1, c2 = st.columns([2, 1])
        with c1:
            st.success(f"🎉 **¡Paquete de georreferenciación ({service_info['badge']}) generado exitosamente!**")
            st.markdown(
                f"El paquete ZIP contiene la cartografía **{service_info['name']}** en archivos **`.tif` + `.tfw`** listos para ser "
                "insertados en AutoCAD mediante `_MAPIINSERT` o `_IMAGEATTACH`."
            )
            st.info(
                "💡 **Consejo para minutas o ámbitos en diagonal en AutoCAD:**\n\n"
                "Para recortar la imagen siguiendo la forma exacta de tu minuta en el dibujo, usa el comando nativo `_IMAGECLIP` (`DELIMIMG`) -> *Nuevo contorno* (`N`) -> *Seleccionar polilínea* (`S`) y selecciona tu polilínea. AutoCAD ocultará las esquinas sobrantes al instante manteniendo la georreferenciación perfecta."
            )
            st.download_button(
                label=f"📥 Descargar Paquete ZIP para AutoCAD ({service_info['badge']})",
                data=st.session_state["processed_zip_data"],
                file_name=st.session_state["processed_zip_name"],
                mime="application/zip",
                use_container_width=True
            )

        with c2:
            zip_mb = len(st.session_state["processed_zip_data"]) / (1024 * 1024)
            st.metric("Tamaño del archivo ZIP", f"{zip_mb:.2f} MB")

        if st.session_state.get("processed_summary"):
            st.write("")
            st.markdown("#### 📑 Resumen de Archivos Generados")
            st.dataframe(pd.DataFrame(st.session_state["processed_summary"]), use_container_width=True, hide_index=True)

    # Pie de página
    st.markdown("---")
    st.markdown("""
    <div style="text-align: center; color: #94a3b8; font-size: 0.85rem; padding: 1.5rem 0; border-top: 1px solid #334155; margin-top: 2rem;">
        <strong style="color: #38bdf8;">AutoCAD PNOA OrthoExtractor</strong> | Integración WMS INSPIRE del Instituto Geográfico Nacional (IGN España)<br>
        Herramienta de automatización SIG para topografía, ingeniería civil y arquitectura.
    </div>
    """, unsafe_allow_html=True)


# --------------------------------------------------------------------------------------
# PUNTO DE ENTRADA PRINCIPAL
# --------------------------------------------------------------------------------------
render_ui()
