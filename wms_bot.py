"""
========================================================================================
Módulo: wms_bot.py
Descripción:
    Asistente Inteligente y Mundial de Servicios WMS para GeoRaster to CAD.
    Cobertura:
      - 🌍 Mundial: España, Europa, América Latina, Estados Unidos, Canadá, Australia y Global.
      - 🤖 Modo Dual: Local Verificado (gratis y offline) + Gemini IA (conversacional).
      - 🔍 Inspector en vivo GetCapabilities para cualquier servidor del planeta.
      - 🔘 Botón Flotante interactivo en la esquina inferior derecha con ventana modal.
========================================================================================
"""

import os
import re
import json
import base64
from pathlib import Path
import xml.etree.ElementTree as ET
import unicodedata
import urllib.parse
from typing import List, Dict, Any, Tuple, Optional, Set
import streamlit as st
import requests
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def get_bot_avatar_path() -> Optional[str]:
    """Retorna la ruta absoluta de la imagen optimizada del avatar del bot."""
    base_dir = Path(__file__).resolve().parent
    web_p = base_dir / "bot_avatar_web.png"
    if web_p.exists():
        return str(web_p)
    orig_p = base_dir / "bot_avatar.png"
    if orig_p.exists():
        return str(orig_p)
    return None


@st.cache_data(show_spinner=False)
def get_bot_avatar_b64() -> str:
    """Retorna la imagen del avatar codificada en Base64 para CSS y elementos HTML."""
    p = get_bot_avatar_path()
    if p and os.path.exists(p):
        try:
            with open(p, "rb") as f:
                return base64.b64encode(f.read()).decode("utf-8")
        except Exception:
            return ""
    return ""

# --------------------------------------------------------------------------------------
# 1. BASE DE DATOS CURADA DE SERVICIOS WMS (MUNDIAL Y REGIONAL)
# --------------------------------------------------------------------------------------
WMS_DATABASE: List[Dict[str, Any]] = [
    # ==========================================
    # 🌍 SERVICIOS GLOBALES Y MUNDIALES
    # ==========================================
    {
        "id": "osm_wms_mundo",
        "name": "OpenStreetMap WMS (Mundial - Calles, Vías y Edificios)",
        "category": "🌐 Servicios Mundiales",
        "region": "Global / Todo el mundo",
        "url": "https://ows.mundialis.de/services/service",
        "default_layer": "OSM-WMS",
        "description": "Cartografía vectorial continua mundial con callejeros, carreteras, hidrografía y edificios de cualquier país.",
        "tags": ["osm", "openstreetmap", "mundial", "global", "calles", "ciudades", "internacional", "carreteras", "world"],
        "layers": [
            ("OSM-WMS", "OpenStreetMap Estándar"),
            ("TOPO-WMS", "Topografía y Relieve OSM"),
            ("OSM-Overlay-WMS", "Transparencia de Carreteras y Rótulos")
        ]
    },
    {
        "id": "nasa_gibs",
        "name": "NASA GIBS (Satélite Diario Global - MODIS / VIIRS)",
        "category": "🌐 Servicios Mundiales",
        "region": "Global / Todo el mundo",
        "url": "https://gibs.earthdata.nasa.gov/wms/epsg4326/best/wms.cgi",
        "default_layer": "MODIS_Terra_CorrectedReflectance_TrueColor",
        "description": "Imágenes satelitales globales actualizadas diariamente por las misiones espaciales Terra y Aqua de la NASA.",
        "tags": ["nasa", "satelite", "diario", "global", "modis", "viirs", "tierra", "clima", "mundial"],
        "layers": [
            ("MODIS_Terra_CorrectedReflectance_TrueColor", "NASA MODIS Color Verdadero Diario"),
            ("VIIRS_SNPP_CorrectedReflectance_TrueColor", "NASA VIIRS Alta Definición")
        ]
    },
    {
        "id": "gebco_bathymetry",
        "name": "GEBCO Grid (Batimetría y Relieve de Océanos y Costas Mundial)",
        "category": "🌐 Servicios Mundiales",
        "region": "Global / Océanos y Costas",
        "url": "https://wms.gebco.net/mapserv",
        "default_layer": "GEBCO_LATEST",
        "description": "Modelo batimétrico continuo global del terreno submarino y relieve costero (GEBCO / UNESCO).",
        "tags": ["batimetria", "mar", "costa", "oceano", "profundidad", "marino", "puerto", "submarino", "gebco"],
        "layers": [
            ("GEBCO_LATEST", "Relieve y Batimetría GEBCO"),
            ("GEBCO_Grid", "GEBCO Grid Global")
        ]
    },

    # ==========================================
    # 🌎 AMÉRICA LATINA
    # ==========================================
    {
        "id": "bogota_ideca_ortofoto",
        "name": "Bogotá - Ortofoto Oficial de Alta Resolución (IDECA / Catastro Distrital)",
        "category": "🌎 América Latina",
        "region": "Bogotá (Colombia)",
        "url": "https://serviciosgis.catastrobogota.gov.co/arcgis/services/imagenes/Ortho2017/MapServer/WMSServer",
        "default_layer": "0",
        "description": "Ortofotomosaico oficial aéreo de máxima resolución de Bogotá D.C. publicado por la Infraestructura de Datos Espaciales de Bogotá (IDECA / Catastro Distrital).",
        "tags": ["bogota", "colombia", "ortofoto", "ortofotos", "ortoimagen", "ortoimagenes", "satelite", "aereo", "foto", "ideca", "catastro"],
        "layers": [("0", "Ortofotomosaico Bogotá D.C. 2017")]
    },
    {
        "id": "bogota_ideca_mapa_referencia",
        "name": "Bogotá - Mapa de Referencia y Catastro (Lotes, Manzanas y Curvas de Nivel - IDECA)",
        "category": "🌎 América Latina",
        "region": "Bogotá (Colombia)",
        "url": "https://serviciosgis.catastrobogota.gov.co/arcgis/services/Mapa_Referencia/Mapa_Referencia/MapServer/WMSServer",
        "default_layer": "15",
        "description": "Cartografía catastral y topográfica oficial de Bogotá: Lotes (capa 15), Manzanas (13), Curvas de nivel (32), Malla vial (42) y Construcciones (14).",
        "tags": ["bogota", "colombia", "catastro", "lote", "lotes", "manzana", "manzanas", "curvas", "nivel", "vias", "calles", "ideca", "parcelas", "topografia"],
        "layers": [
            ("15", "Lote Catastral Bogotá"),
            ("13", "Manzana Catastral Bogotá"),
            ("32", "Curvas de Nivel Bogotá"),
            ("42", "Malla Vial Bogotá"),
            ("14", "Construcciones Bogotá")
        ]
    },
    {
        "id": "colombia_igac_carto",
        "name": "Colombia - Cartografía Básica Oficial (IGAC)",
        "category": "🌎 América Latina",
        "region": "Colombia",
        "url": "https://mapas2.igac.gov.co/server/services/carto/carto100000colombia2019/MapServer/WMSServer",
        "default_layer": "34",
        "description": "Cartografía topográfica oficial del Instituto Geográfico Agustín Codazzi (IGAC) de Colombia: vías, orografía, drenajes y límites.",
        "tags": ["colombia", "igac", "bogota", "medellin", "cali", "cartografia", "topografia", "magna", "sirgas", "nacional", "vias", "orografia"],
        "layers": [
            ("34", "Vías e Infraestructura"),
            ("21", "Límites Administrativos"),
            ("39", "Orografía y Relieve"),
            ("24", "Hidrografía (Drenaje Sencillo)"),
            ("0", "Bosques y Coberturas"),
            ("20", "Construcciones")
        ]
    },
    {
        "id": "colombia_igac_municipios",
        "name": "Colombia - Municipios y Límites Político-Administrativos (IGAC)",
        "category": "🌎 América Latina",
        "region": "Colombia",
        "url": "https://mapas2.igac.gov.co/server/services/carto/municipios/MapServer/WMSServer",
        "default_layer": "0",
        "description": "Límites departamentales y municipales oficiales de Colombia certificados por el IGAC.",
        "tags": ["colombia", "igac", "municipios", "limites", "fronteras", "departamentos", "politico", "division"],
        "layers": [("0", "Municipios y Departamentos de Colombia")]
    },
    {
        "id": "medellin_geomedellin",
        "name": "Medellín - Geoportal y Cartografía Oficial (GeoMedellín)",
        "category": "🌎 América Latina",
        "region": "Medellín (Colombia)",
        "url": "https://www.medellin.gov.co/geoserver/wms",
        "default_layer": "medellin_base",
        "description": "Cartografía base municipal, comunas, barrios y red vial de Medellín (Alcaldía de Medellín).",
        "tags": ["medellin", "antioquia", "colombia", "cartografia", "barrios", "catastro", "geomedellin"],
        "layers": [("medellin_base", "Cartografía Base Medellín")]
    },
    {
        "id": "cali_idecali",
        "name": "Cali - Infraestructura de Datos Espaciales (IDESC / Alcaldía de Cali)",
        "category": "🌎 América Latina",
        "region": "Cali (Colombia)",
        "url": "https://ws-idesc.cali.gov.co/geoserver/wms",
        "default_layer": "Mapa base",
        "description": "Cartografía oficial del Distrito de Santiago de Cali (IDESC / Alcaldía de Cali): base urbana, comunas y equipamientos.",
        "tags": ["cali", "valle", "colombia", "cartografia", "barrios", "idecali", "idesc"],
        "layers": [
            ("Mapa base", "Mapa Base Oficial Cali"),
            ("cultura:acpc_tdf_festivales", "Equipamientos y Cultura"),
            ("salud:ads_afiliados_eps", "Infraestructura")
        ]
    },
    {
        "id": "colombia_sgc_geologia",
        "name": "Colombia - Atlas Geológico Oficial (Servicio Geológico Colombiano)",
        "category": "🌎 América Latina",
        "region": "Colombia",
        "url": "https://srvags.sgc.gov.co/arcgis/services/Atlas_Geologico_2015/Atlas_Geologico_2015/MapServer/WMSServer",
        "default_layer": "0",
        "description": "Mapa geológico oficial continuo a escala 1:500.000 y fallas activas de Colombia (SGC).",
        "tags": ["colombia", "geologia", "sgc", "fallas", "rocas", "mineria", "geotecnia", "bogota", "medellin"],
        "layers": [("0", "Atlas Geológico de Colombia 2015")]
    },
    {
        "id": "mexico_inegi_topo",
        "name": "México - Cartografía Topográfica Nacional (INEGI)",
        "category": "🌎 América Latina",
        "region": "México",
        "url": "https://gaia.inegi.org.mx/NLB/tunnel/wms/wms61",
        "default_layer": "Datos del relieve",
        "description": "Información topográfica oficial con curvas de nivel, localidades y orografía del INEGI de México.",
        "tags": ["mexico", "inegi", "cdmx", "guadalajara", "monterrey", "curvas", "nivel", "topografia", "elevacion", "relieve"],
        "layers": [
            ("Datos del relieve", "Datos del Relieve e Hipsometría INEGI"),
            ("Servicio_WMS_MDM61", "Mosaico Cartográfico Digital de México")
        ]
    },
    {
        "id": "chile_ide_snit",
        "name": "Chile - Infraestructura de Datos Espaciales (IDE Chile / MMA)",
        "category": "🌎 América Latina",
        "region": "Chile",
        "url": "https://ide.mma.gob.cl/geoserver/wms",
        "default_layer": "spearfish",
        "description": "Cartografía territorial, ambiental y coberturas temáticas de Chile (Ministerio del Medio Ambiente / IDE Chile).",
        "tags": ["chile", "santiago", "valparaiso", "concepcion", "ide", "snit", "mma"],
        "layers": [("spearfish", "Cartografía Temática Chile MMA")]
    },
    {
        "id": "argentina_idecor",
        "name": "Argentina - Cartografía y Catastro IDECOR (Infraestructura de Datos Espaciales)",
        "category": "🌎 América Latina",
        "region": "Argentina",
        "url": "https://idecor-ws.mapascordoba.gob.ar/geoserver/idecor/wms",
        "default_layer": "bpa2019",
        "description": "Cartografía catastral, parcelas rurales y urbanas, vialidad y usos del suelo de Argentina (IDECOR / IDE).",
        "tags": ["argentina", "buenos aires", "cordoba", "rosario", "idecor", "catastro", "parcelas", "suelo"],
        "layers": [("bpa2019", "Coberturas y Parcelas IDECOR")]
    },
    {
        "id": "peru_geocatmin",
        "name": "Perú - GEOCATMIN (Catastro Minero y Geología - INGEMMET)",
        "category": "🌎 América Latina",
        "region": "Perú",
        "url": "https://geocatmin.ingemmet.gob.pe/arcgis/services/SERV_CATASTRO_MINERO_WGS84/MapServer/WMSServer",
        "default_layer": "0",
        "description": "Catastro Minero Nacional oficial y concesiones mineras de Perú (INGEMMET / GEOCATMIN).",
        "tags": ["peru", "lima", "arequipa", "ingemmet", "geologia", "mineria", "catastro"],
        "layers": [("0", "Catastro Minero Nacional Perú")]
    },

    # ==========================================
    # 🦅 ESTADOS UNIDOS Y CANADÁ
    # ==========================================
    {
        "id": "usgs_topo",
        "name": "EE.UU. - USGS The National Map (Topografía y Curvas de Nivel)",
        "category": "🦅 Norteamérica",
        "region": "Estados Unidos (EE.UU.)",
        "url": "https://basemap.nationalmap.gov/arcgis/services/USGSImageryTopo/MapServer/WMSServer",
        "default_layer": "0",
        "description": "Servicio oficial del U.S. Geological Survey (USGS) que integra imágenes aéreas de alta resolución y curvas topográficas.",
        "tags": ["usa", "eeuu", "estados unidos", "usgs", "topo", "imagery", "curvas", "elevacion"],
        "layers": [("0", "USGS Imagery Topo")]
    },
    {
        "id": "usgs_hydrography",
        "name": "EE.UU. - National Hydrography Dataset (USGS NHD)",
        "category": "🦅 Norteamérica",
        "region": "Estados Unidos (EE.UU.)",
        "url": "https://hydro.nationalmap.gov/arcgis/services/nhd/MapServer/WMSServer",
        "default_layer": "0",
        "description": "Red hidrográfica completa de Estados Unidos: ríos, arroyos, cuencas y masas de agua.",
        "tags": ["usa", "eeuu", "usgs", "nhd", "hidrografia", "rios", "agua"],
        "layers": [("0", "NHD Hydrography")]
    },
    {
        "id": "noaa_charts",
        "name": "EE.UU. - Cartas Náuticas Oficiales (NOAA Maritime)",
        "category": "🦅 Norteamérica",
        "region": "Estados Unidos (Costas)",
        "url": "https://gis.charttools.noaa.gov/arcgis/rest/services/MCS/ENCOnline/MapServer/exts/MaritimeChartService/WMSServer",
        "default_layer": "0",
        "description": "Cartas náuticas electrónicas oficiales (ENC) de navegación marina y batimetría costera de la NOAA.",
        "tags": ["usa", "noaa", "nautica", "mar", "costa", "navegacion", "puertos"],
        "layers": [("0", "NOAA Electronic Navigational Charts")]
    },
    {
        "id": "canada_canvec",
        "name": "Canadá - CanVec Topografía Nacional (NRCan)",
        "category": "🦅 Norteamérica",
        "region": "Canadá",
        "url": "https://maps.geogratis.gc.ca/wms/canvec_en",
        "default_layer": "canvec",
        "description": "Producto cartográfico vectorial de referencia de Recursos Naturales de Canadá (NRCan).",
        "tags": ["canada", "nrcan", "canvec", "ontario", "quebec", "vancouver", "topo"],
        "layers": [("canvec", "CanVec Topography")]
    },

    # ==========================================
    # 🇪🇺 EUROPA E INTERNACIONAL
    # ==========================================
    {
        "id": "copernicus_clc",
        "name": "Europa - Copernicus Corine Land Cover (Unión Europea)",
        "category": "🇪🇺 Europa",
        "region": "Europa (Unión Europea)",
        "url": "https://copernicus.discomap.eea.europa.eu/arcgis/services/Corine/CLC2018_WM/MapServer/WMSServer",
        "default_layer": "1",
        "description": "Inventario oficial europeo de ocupación del suelo (CORINE Land Cover) de la Agencia Europea de Medio Ambiente (EEA).",
        "tags": ["europa", "copernicus", "clc", "corine", "suelo", "vegetacion", "urbano", "union europea"],
        "layers": [
            ("1", "CORINE Land Cover 2018"),
            ("2", "Land Cover Changes")
        ]
    },
    {
        "id": "francia_ign",
        "name": "Francia - Cartes Topographiques & Orthophoto (IGN Géoportail)",
        "category": "🇪🇺 Europa",
        "region": "Francia",
        "url": "https://data.geopf.fr/wms-r",
        "default_layer": "GEOGRAPHICALGRIDSYSTEMS.PLANIGNV2",
        "description": "Cartografía topográfica oficial del Institut National de l'Information Géographique et Forestière (IGN Francia).",
        "tags": ["francia", "france", "paris", "ign france", "geoportail", "ortho", "topo"],
        "layers": [
            ("GEOGRAPHICALGRIDSYSTEMS.PLANIGNV2", "Plan IGN Topographique"),
            ("ORTHOIMAGERY.ORTHOPHOTOS", "BD ORTHO Photographie Aérienne")
        ]
    },
    {
        "id": "alemania_bkg",
        "name": "Alemania - TopPlusOpen & Basemap (BKG)",
        "category": "🇪🇺 Europa",
        "region": "Alemania",
        "url": "https://sgx.geodatenzentrum.de/wms_topplus_open",
        "default_layer": "web",
        "description": "Cartografía oficial federal alemana del Bundesamt für Kartographie und Geodäsie (BKG).",
        "tags": ["alemania", "germany", "deutschland", "berlin", "bkg", "topplus"],
        "layers": [("web", "TopPlusOpen Deutschland")]
    },
    {
        "id": "portugal_dgt",
        "name": "Portugal - OrtoSat Satélite de Alta Resolução (DGT)",
        "category": "🇪🇺 Europa",
        "region": "Portugal",
        "url": "https://ortos.dgterritorio.gov.pt/wms/ortosat2023",
        "default_layer": "OrtoSat2023",
        "description": "Ortofotomosaicos satelitais oficiais de alta resolução da Direção-Geral do Território (DGT) de Portugal.",
        "tags": ["portugal", "lisboa", "porto", "dgt", "ortofoto", "snig", "ortosat"],
        "layers": [
            ("OrtoSat2023", "OrtoSat 2023 Alta Definição"),
            ("ortoSat2023-CorVerdadeira", "OrtoSat Cor Verdadeira")
        ]
    },
    {
        "id": "australia_dea",
        "name": "Australia - Digital Earth Australia (Geoscience Australia)",
        "category": "🌐 Servicios Mundiales",
        "region": "Australia",
        "url": "https://ows.dea.ga.gov.au/wms",
        "default_layer": "ga_ls_ard_3",
        "description": "Mosaicos y cubos de datos satelitales calibrados de todo el continente australiano (Geoscience Australia).",
        "tags": ["australia", "sydney", "melbourne", "geoscience", "dea", "landsat", "gda2020", "ortofoto", "satelite"],
        "layers": [("ga_ls_ard_3", "DEA Surface Reflectance Australia")]
    },
    {
        "id": "australia_topo",
        "name": "Australia - Topografía Nacional y Relieve (Geoscience Australia)",
        "category": "🗺️ Topografía y Relieve",
        "region": "Australia",
        "url": "https://services.ga.gov.au/gis/services/Topographic_Base_Map_WM/MapServer/WMSServer",
        "default_layer": "0",
        "description": "Mapa topográfico base nacional con curvas de nivel, relieve y elevación de Australia (Geoscience Australia).",
        "tags": ["australia", "topografia", "curvas", "relieve", "elevacion", "geoscience", "mapa", "sydney", "melbourne", "gda2020"],
        "layers": [("0", "Topographic Base Map Australia")]
    },
    {
        "id": "australia_hydrology",
        "name": "Australia - Hidrología y Masas de Agua (Geoscience Australia)",
        "category": "🌊 Aguas, Costas e Inundabilidad",
        "region": "Australia",
        "url": "https://services.ga.gov.au/gis/services/Surface_Hydrology/MapServer/WMSServer",
        "default_layer": "0",
        "description": "Red hidrográfica nacional de ríos, cuencas, lagos y masas de agua de Australia (Geoscience Australia).",
        "tags": ["australia", "hidrologia", "agua", "rios", "cauces", "cuencas", "geoscience", "aguas"],
        "layers": [("0", "Surface Hydrology Network")]
    },
    {
        "id": "australia_cadastre_nsw",
        "name": "Australia - Catastro Oficial (NSW SIX Maps)",
        "category": "🏛️ Catastro y Parcelario",
        "region": "Australia",
        "url": "https://maps.six.nsw.gov.au/arcgis/services/public/NSW_Cadastre/MapServer/WMSServer",
        "default_layer": "0",
        "description": "Cartografía catastral de parcelas, límites de propiedad y predios de Nueva Gales del Sur / Sydney (Spatial Services NSW SIX Maps).",
        "tags": ["australia", "catastro", "parcelas", "nsw", "sydney", "parcelario", "predios", "lotes", "six"],
        "layers": [("0", "NSW Land Cadastre")]
    },
    {
        "id": "australia_cadastre_portal",
        "name": "Australia - Catastro y Parcelario (NSW Spatial Collaboration Portal)",
        "category": "🏛️ Catastro y Parcelario",
        "region": "Australia",
        "url": "https://portal.spatial.nsw.gov.au/server/services/Cadastre_History/MapServer/WMSServer",
        "default_layer": "0",
        "description": "Servicio moderno de parcelas y catastro oficial del Spatial Collaboration Portal de NSW (DCS Spatial Services).",
        "tags": ["australia", "catastro", "parcelas", "nsw", "sydney", "parcelario", "portal", "dcs", "history"],
        "layers": [("0", "NSW Cadastre Service")]
    },
    {
        "id": "australia_geology",
        "name": "Australia - Geología y Recursos Naturales (Geoscience Australia)",
        "category": "🗺️ Topografía y Relieve",
        "region": "Australia",
        "url": "https://services.ga.gov.au/gis/services/GA_Surface_Geology/MapServer/WMSServer",
        "default_layer": "0",
        "description": "Cartografía geológica de superficie, litología y unidades estructurales de Australia (Geoscience Australia).",
        "tags": ["australia", "geologia", "suelos", "litologia", "rocas", "geoscience", "mineria", "gda2020"],
        "layers": [("0", "Surface Geology Australia")]
    },
    {
        "id": "australia_landcover",
        "name": "Australia - Suelos y Coberturas Vegetales (DEA Land Cover)",
        "category": "🌲 Medio Ambiente y Montes",
        "region": "Australia",
        "url": "https://services.ga.gov.au/gis/services/DEA_Land_Cover/MapServer/WMSServer",
        "default_layer": "0",
        "description": "Clasificación de coberturas de la tierra, vegetación y usos del suelo de Australia (Digital Earth Australia).",
        "tags": ["australia", "suelos", "usos del suelo", "coberturas", "vegetacion", "dea", "geoscience", "cultivos"],
        "layers": [("0", "DEA Land Cover 25m")]
    },

    # ==========================================
    # 🇪🇸 ESPAÑA (NACIONAL Y AUTONÓMICO)
    # ==========================================
    {
        "id": "catastro_nacional",
        "name": "España - Sede Electrónica del Catastro (DGC)",
        "category": "🏛️ Catastro y Parcelario",
        "region": "España (Nacional)",
        "url": "https://ovc.catastro.meh.es/Cartografia/WMS/ServidorWMS.aspx",
        "default_layer": "Catastro",
        "description": "Cartografía catastral oficial completa: parcelas rústicas y urbanas, subparcelas, números de policía, manzanas y linderos.",
        "tags": ["catastro", "parcela", "parcelas", "finca", "linderos", "subparcela", "urbana", "rustica", "inmueble", "dgc"],
        "layers": [
            ("Catastro", "Capa completa integrada (Parcelas, Manzanas y Números)"),
            ("CONSTRU", "Construcciones Catastrales"),
            ("PARCELA", "Límites geométricos de parcelas"),
            ("SUBPARCELA", "Subparcelas y recintos de cultivo"),
            ("MASA", "Manzanas y masas catastrales"),
            ("NUMERO", "Números de portal / policía")
        ]
    },
    {
        "id": "catastro_inspire",
        "name": "España - Catastro INSPIRE Oficial (Directiva Europea)",
        "category": "🏛️ Catastro y Parcelario",
        "region": "España (Nacional)",
        "url": "https://ovc.catastro.meh.es/cartografia/INSPIRE/spadgcwms.aspx",
        "default_layer": "CP.CadastralParcel",
        "description": "Servicio WMS INSPIRE de la Dirección General del Catastro, estandarizado con codificación europea.",
        "tags": ["catastro", "inspire", "parcelas", "parcel", "cadastral", "europa"],
        "layers": [
            ("CP.CadastralParcel", "Parcelas Catastrales INSPIRE"),
            ("CP.CadastralZoning", "Zonas Catastrales (Polígonos / Manzanas)"),
            ("AD.Address", "Direcciones Postales Oficiales")
        ]
    },
    {
        "id": "catastro_navarra",
        "name": "Navarra - Catastro Foral (IDENA)",
        "category": "🏛️ Catastro y Parcelario",
        "region": "Navarra (España)",
        "url": "https://idena.navarra.es/ogc/wms",
        "default_layer": "catastro",
        "description": "Parcelario y riqueza territorial foral de Navarra.",
        "tags": ["catastro", "navarra", "idena", "pamplona", "foral", "parcelas"],
        "layers": [("catastro", "Catastro Oficial de Navarra")]
    },
    {
        "id": "catastro_bizkaia",
        "name": "Bizkaia - Catastro Foral (País Vasco)",
        "category": "🏛️ Catastro y Parcelario",
        "region": "País Vasco (España)",
        "url": "https://geo.bizkaia.eus/arcgisserverinspire/rest/services/Catastro/Annex1/MapServer/exts/InspireView/service",
        "default_layer": "CP.CadastralParcel",
        "description": "Cartografía parcelaria del Catastro de la Diputación Foral de Bizkaia (INSPIRE).",
        "tags": ["catastro", "bizkaia", "vizcaya", "bilbao", "euskadi", "foral"],
        "layers": [
            ("CP.CadastralParcel", "Parcelas Forales de Bizkaia"),
            ("CP.CadastralZoning", "Zonificación Catastral"),
            ("AD.Address", "Direcciones y Portales Bizkaia")
        ]
    },
    {
        "id": "catastro_araba",
        "name": "Álava - Catastro Foral (País Vasco)",
        "category": "🏛️ Catastro y Parcelario",
        "region": "País Vasco (España)",
        "url": "https://geo.araba.eus/WMS_Katastroa",
        "default_layer": "Hirilurzatien_funtsa_Fondo_ParcelasUrbanas",
        "description": "Parcelario y delimitaciones catastrales de la Diputación Foral de Álava.",
        "tags": ["catastro", "alava", "araba", "vitoria", "euskadi", "foral"],
        "layers": [
            ("Hirilurzatien_funtsa_Fondo_ParcelasUrbanas", "Parcelas Urbanas"),
            ("Udalerriak_Municipios", "Límites Municipales Álava")
        ]
    },
    {
        "id": "mapa_raster_ign",
        "name": "España - Cartografía Topográfica Ráster (MTN25 / MTN50 - IGN)",
        "category": "🗺️ Topografía y Relieve",
        "region": "España (Nacional)",
        "url": "https://www.ign.es/wms-inspire/mapa-raster",
        "default_layer": "mtn_rasterizado",
        "description": "Cartografía oficial con curvas de nivel, toponimia, caminos, pistas y altitudes de las series MTN25 y MTN50.",
        "tags": ["curvas", "nivel", "topografia", "topografico", "altitud", "cota", "ign", "mtn", "mtn25", "mtn50"],
        "layers": [("mtn_rasterizado", "Mapa Topográfico Nacional Rasterizado continuo")]
    },
    {
        "id": "mdt_relieve_ign",
        "name": "España - Relieve Sombreado LiDAR y MDT (IGN)",
        "category": "🗺️ Topografía y Relieve",
        "region": "España (Nacional)",
        "url": "https://servicios.idee.es/wms-inspire/mdt",
        "default_layer": "EL.ElevationGridCoverage",
        "description": "Sombreado continuo del terreno de alta precisión generado a partir de vuelos LiDAR y MDT del IGN.",
        "tags": ["mdt", "dem", "relieve", "sombreado", "lidar", "elevacion", "terreno", "montaña", "altimetria"],
        "layers": [("EL.ElevationGridCoverage", "Sombreado de Relieve Continuo LiDAR")]
    },
    {
        "id": "mdp_pendientes_ign",
        "name": "España - Modelo Digital de Pendientes (MDP05 - IGN)",
        "category": "🗺️ Topografía y Relieve",
        "region": "España (Nacional)",
        "url": "https://wms-pendientes.idee.es/pendientes",
        "default_layer": "MDP05",
        "description": "Mapa continuo de pendientes y desniveles del terreno derivado de vuelos LiDAR (resolución 5m).",
        "tags": ["pendientes", "pendiente", "inclinacion", "desnivel", "mdp", "mdp05", "talud"],
        "layers": [("MDP05", "Modelo Digital de Pendientes 5m")]
    },
    {
        "id": "snczi_inundabilidad",
        "name": "España - Zonas Inundables SNCZI (MITECO - T=10, 50, 100 y 500 años)",
        "category": "🌊 Aguas e Inundabilidad",
        "region": "España (Nacional)",
        "url": "https://wms.mapama.gob.es/sig/Agua/SNCZI/wms.aspx",
        "default_layer": "ZI_T100",
        "description": "Mapas oficiales de peligrosidad y riesgo de inundación para períodos de retorno T=10, T=50, T=100 y T=500 años.",
        "tags": ["inundable", "inundacion", "inundaciones", "snczi", "peligrosidad", "riesgo", "retorno", "t100", "t500", "miteco"],
        "layers": [
            ("ZI_T100", "Zonas Inundables - Periodo de Retorno 100 años (T=100)"),
            ("ZI_T500", "Zonas Inundables - Periodo de Retorno 500 años (T=500)"),
            ("ZI_T50", "Zonas Inundables - Periodo de Retorno 50 años (T=50)"),
            ("ZI_T10", "Zonas Inundables - Periodo de Retorno 10 años (T=10)"),
            ("ARPSI", "Áreas de Riesgo Potencial Significativo de Inundación")
        ]
    },
    {
        "id": "dph_miteco",
        "name": "España - Dominio Público Hidráulico y Servidumbres (DPH - MITECO)",
        "category": "🌊 Aguas e Inundabilidad",
        "region": "España (Nacional)",
        "url": "https://wms.mapama.gob.es/sig/Agua/DPH/wms.aspx",
        "default_layer": "DPH",
        "description": "Límites del Dominio Público Hidráulico, servidumbre (5 m) y zonas de policía (100 m) de cauces públicos.",
        "tags": ["dph", "dominio publico", "hidraulico", "servidumbre", "policia", "cauce", "rio", "arroyo", "ribera"],
        "layers": [
            ("DPH", "Dominio Público Hidráulico Cartografiado"),
            ("ZonaServidumbre", "Zona de Servidumbre (5 m)"),
            ("ZonaPolicia", "Zona de Policía (100 m)")
        ]
    },
    {
        "id": "hidrografia_igr",
        "name": "España - Hidrografía Oficial de Referencia (IGR - IGN / MITECO)",
        "category": "🌊 Aguas e Inundabilidad",
        "region": "España (Nacional)",
        "url": "https://servicios.idee.es/wms-inspire/hidrografia",
        "default_layer": "HY.Network",
        "description": "Red hidrográfica continua: ríos, arroyos, ramblas, canales, lagos, embalses y cuencas.",
        "tags": ["rio", "rios", "arroyo", "embalse", "lago", "cuenca", "hidrografia", "agua"],
        "layers": [
            ("HY.Network", "Red Hidrográfica Oficial"),
            ("HY.PhysicalWaters.Waterbodies", "Masas de Agua (Embalses, Lagos)")
        ]
    },
    {
        "id": "geode_igme",
        "name": "España - Mapa Geológico Continuo GEODE (1:50.000 - IGME)",
        "category": "⛰️ Geología y Geotecnia",
        "region": "España (Nacional)",
        "url": "https://info.igme.es/cartografiadigital/geomaestro/wms.aspx",
        "default_layer": "GEODE_50",
        "description": "Cartografía geológica digital continua a escala 1:50.000 del Instituto Geológico y Minero de España.",
        "tags": ["geologia", "geologico", "igme", "litologia", "rocas", "fallas", "geotecnia", "geode"],
        "layers": [
            ("GEODE_50", "Mapa Geológico Continuo 1:50.000 (GEODE)"),
            ("MAGNA_50", "Hojas del Mapa Geológico Nacional (MAGNA 50)")
        ]
    },
    {
        "id": "red_natura_2000",
        "name": "España - Red Natura 2000 (LIC, ZEC y ZEPA - MITECO)",
        "category": "🌲 Medio Ambiente y Montes",
        "region": "España (Nacional)",
        "url": "https://wms.mapama.gob.es/sig/Biodiversidad/RN2000/wms.aspx",
        "default_layer": "RN2000",
        "description": "Espacios protegidos de la Red Natura 2000: Lugares de Importancia Comunitaria (LIC), Zonas Especiales de Conservación (ZEC) y Zonas de Especial Protección para las Aves (ZEPA).",
        "tags": ["natura", "red natura", "lic", "zec", "zepa", "aves", "protegido", "conservacion", "miteco"],
        "layers": [
            ("RN2000", "Red Natura 2000 Completa"),
            ("LIC", "Lugares de Importancia Comunitaria (LIC/ZEC)"),
            ("ZEPA", "Zonas de Especial Protección para las Aves (ZEPA)")
        ]
    },
    {
        "id": "espacios_protegidos_enp",
        "name": "España - Espacios Naturales Protegidos (ENP - MITECO)",
        "category": "🌲 Medio Ambiente y Montes",
        "region": "España (Nacional)",
        "url": "https://wms.mapama.gob.es/sig/Biodiversidad/ENP/wms.aspx",
        "default_layer": "ENP",
        "description": "Parques Nacionales, Parques Naturales, Reservas y Monumentos Naturales de España.",
        "tags": ["parque", "nacional", "natural", "reserva", "enp", "espacio protegido"],
        "layers": [("ENP", "Espacios Naturales Protegidos")]
    },
    {
        "id": "montes_utilidad_publica_mup",
        "name": "España - Montes de Utilidad Pública (MUP - MITECO)",
        "category": "🌲 Medio Ambiente y Montes",
        "region": "España (Nacional)",
        "url": "https://wms.mapama.gob.es/sig/Biodiversidad/MUP/wms.aspx",
        "default_layer": "MUP",
        "description": "Catálogo oficial de Montes de Utilidad Pública (MUP), demaniales y comunales protegidos de España (MITECO).",
        "tags": ["montes", "mup", "forestal", "medio ambiente", "monte", "utilidad publica", "bosque", "espana"],
        "layers": [("MUP", "Montes de Utilidad Pública de España")]
    },
    {
        "id": "pnoa_maxima_actualidad",
        "name": "España - PNOA Máxima Actualidad (IGN - Vuelo Oficial)",
        "category": "🛰️ Ortofotografía y Satélite",
        "region": "España (Nacional)",
        "url": "https://www.ign.es/wms-inspire/pnoa-ma",
        "default_layer": "OI.OrthoimageCoverage",
        "description": "Ortofotos aéreas de máxima resolución y actualidad del Plan Nacional de Ortofotografía Aérea (25-50 cm/px).",
        "tags": ["pnoa", "ortofoto", "ortofotografia", "satelite", "aerea", "alta resolucion", "ign"],
        "layers": [("OI.OrthoimageCoverage", "Ortoimagen PNOA Máxima Actualidad")]
    },
    {
        "id": "fototeca_historica_ign",
        "name": "España - Fototeca Histórica (Vuelo Americano 1956 y Años 30/40)",
        "category": "🛰️ Ortofotografía y Satélite",
        "region": "España (Nacional)",
        "url": "https://wms-fototeca.idee.es/fototeca",
        "default_layer": "anos50",
        "description": "Vuelo fotográfico militar Americano de la Serie B (1956-1957) y fotogramas aéreos históricos de los años 30 y 40.",
        "tags": ["americano", "vuelo americano", "1956", "1957", "fototeca", "blanco y negro", "historica"],
        "layers": [
            ("anos50", "Vuelo Americano Serie B (1956-1957)"),
            ("anos40", "Vuelos de los años 40"),
            ("anos30", "Fotogramas de los años 30")
        ]
    },

    # --- AUTONÓMICOS ESPAÑA ---
    {
        "id": "andalucia_rediam",
        "name": "Andalucía - Ortofoto de Alta Resolución (REDIAM)",
        "category": "🏛️ Comunidades Autónomas (España)",
        "region": "Andalucía (España)",
        "url": "https://www.juntadeandalucia.es/medioambiente/mapwms/REDIAM_Ortofoto_2020",
        "default_layer": "ortofoto_2020",
        "description": "Ortofotografía aérea de máxima resolución de la Junta de Andalucía (REDIAM).",
        "tags": ["andalucia", "sevilla", "malaga", "granada", "cordoba", "cadiz", "jaen", "almeria", "huelva", "rediam"],
        "layers": [("ortofoto_2020", "Ortofoto Andalucía")]
    },
    {
        "id": "cataluna_icgc",
        "name": "Cataluña - Ortofoto y Topografía (ICGC)",
        "category": "🏛️ Comunidades Autónomas (España)",
        "region": "Cataluña (España)",
        "url": "https://geoserveis.icgc.cat/icc_mapesmultibase/noutm/wms/service",
        "default_layer": "orto",
        "description": "Institut Cartogràfic i Geològic de Catalunya: Ortofotos nítidas de 10-25 cm y mapas topográficos.",
        "tags": ["cataluña", "catalunya", "barcelona", "girona", "lleida", "tarragona", "icgc", "ortofoto"],
        "layers": [
            ("orto", "Ortofoto de Catalunya de Máxima Resolución"),
            ("topo", "Mapa Topográfico de Catalunya")
        ]
    },
    {
        "id": "euskadi_gipuzkoa_orto",
        "name": "País Vasco / Gipuzkoa - Ortofotografía Oficial de Alta Resolución (b5m)",
        "category": "🏛️ Comunidades Autónomas (España)",
        "region": "País Vasco (España)",
        "url": "https://b5m.gipuzkoa.eus/ogc/wms/gipuzkoa_ort_wms",
        "default_layer": "orto",
        "description": "Ortofotografías oficiales de máxima resolución y vuelos recientes del territorio vasco (b5m).",
        "tags": ["euskadi", "pais vasco", "gipuzkoa", "san sebastian", "donostia", "ortofoto", "b5m"],
        "layers": [
            ("orto", "Ortofoto Actualizada Gipuzkoa"),
            ("orto2025", "Ortofoto Vuelo 2025"),
            ("orto2024", "Ortofoto Vuelo 2024")
        ]
    },
    {
        "id": "euskadi_medio_ambiente",
        "name": "País Vasco / Euskadi - Medio Ambiente y Territorio (GeoEuskadi)",
        "category": "🏛️ Comunidades Autónomas (España)",
        "region": "País Vasco (España)",
        "url": "https://www.geo.euskadi.eus/WMS_INGURUMENA",
        "default_layer": "has_espacios_naturales_protegidos",
        "description": "Espacios naturales, energía y capas ambientales oficiales del Gobierno Vasco (GeoEuskadi).",
        "tags": ["euskadi", "pais vasco", "geoeuskadi", "medio ambiente", "protegido", "energia", "ingurumena"],
        "layers": [("has_espacios_naturales_protegidos", "Espacios Naturales Protegidos Euskadi")]
    },
    {
        "id": "madrid_ayto",
        "name": "Madrid - Ortofoto Oficial de Máxima Resolución (Ayuntamiento de Madrid)",
        "category": "🏛️ Comunidades Autónomas (España)",
        "region": "Madrid (España)",
        "url": "https://servpub.madrid.es/georaster/ORTOFOTOS/ORTOFOTO_MADRID/ows",
        "default_layer": "ORTOFOTO_MADRID",
        "description": "Ortofotografía verdadera aérea oficial de máxima precisión del término municipal de Madrid.",
        "tags": ["madrid", "capital", "ayuntamiento", "ortofoto", "vuelo", "satelite"],
        "layers": [("ORTOFOTO_MADRID", "Ortofoto Oficial Madrid")]
    },
    {
        "id": "galicia_ideg",
        "name": "Galicia - Ortoimaxes PNOA Máxima Resolución (IDEG / Xunta de Galicia)",
        "category": "🏛️ Comunidades Autónomas (España)",
        "region": "Galicia (España)",
        "url": "https://ideg.xunta.es/servizos/services/Raster/PNOA_2020/ImageServer/WMSServer",
        "default_layer": "0",
        "description": "Ortoimágenes aéreas actualizadas de 15 cm/píxel de la Xunta de Galicia e Instituto de Estudos do Territorio.",
        "tags": ["galicia", "coruña", "lugo", "ourense", "pontevedra", "xunta", "ideg", "vigo", "santiago", "ortofoto"],
        "layers": [("0", "Ortoimaxe PNOA Galicia")]
    },
    {
        "id": "valencia_icv",
        "name": "Comunidad Valenciana - Base Cartográfica Oficial CV05 (ICV / Terramapas)",
        "category": "🏛️ Comunidades Autónomas (España)",
        "region": "Comunidad Valenciana (España)",
        "url": "https://terramapas.icv.gva.es/0101_BCV05",
        "default_layer": "OWS_0101_BCV05",
        "description": "Institut Cartogràfic Valencià: Cartografía base topográfica continua 1:5.000 con entornos urbanos y viales.",
        "tags": ["valencia", "valenciana", "alicante", "castellon", "icv", "gva", "terramapas", "topografia", "cv05", "ortofoto"],
        "layers": [
            ("OWS_0101_BCV05", "Base Cartográfica CV05 Completa"),
            ("EntornosUrbanosBCV05", "Entornos Urbanos y Viales"),
            ("CultivosBCV05", "Cultivos y Zonas Rústicas")
        ]
    },
    {
        "id": "valencia_ortofoto_icv",
        "name": "Comunidad Valenciana - Ortofoto Oficial de Alta Resolución (ICV / Terramapas)",
        "category": "🏛️ Comunidades Autónomas (España)",
        "region": "Comunidad Valenciana (España)",
        "url": "https://terramapas.icv.gva.es/0202_2023_PNOA_25cm",
        "default_layer": "0202_2023_PNOA_25cm",
        "description": "Institut Cartogràfic Valencià: Ortofoto oficial de máxima resolución PNOA 25 cm/px de la Comunitat Valenciana.",
        "tags": ["valencia", "valenciana", "alicante", "castellon", "icv", "ortofoto", "satelite", "pnoa", "terramapas"],
        "layers": [
            ("0202_2023_PNOA_25cm", "Ortofoto Comunitat Valenciana 25 cm")
        ]
    },
    {
        "id": "canarias_grafcan",
        "name": "Canarias - Ortofoto Oficial de Alta Resolución (GRAFCAN)",
        "category": "🏛️ Comunidades Autónomas (España)",
        "region": "Canarias (España)",
        "url": "https://idecan1.grafcan.es/ServicioWMS/Historico/Ortofotos/Ortofoto2025",
        "default_layer": "ortofoto",
        "description": "Infraestructura de Datos Espaciales de Canarias (GRAFCAN / IDECanarias): Vuelo ortofotográfico oficial de las islas.",
        "tags": ["canarias", "grafcan", "tenerife", "gran canaria", "palma", "lanzarote", "fuerteventura", "ortofoto"],
        "layers": [
            ("ortofoto", "Ortofoto Máxima Actualidad Canarias"),
            ("WMS_Ortofoto2025", "Mosaico Ortofoto Canarias")
        ]
    },
    {
        "id": "baleares_ideib",
        "name": "Islas Baleares - Mapa Base y Cartografía Oficial (IDEIB)",
        "category": "🏛️ Comunidades Autónomas (España)",
        "region": "Islas Baleares (España)",
        "url": "https://ideib.caib.es/geoserveis/services/public/GOIB_MapaBase_IB/MapServer/WMSServer",
        "default_layer": "0",
        "description": "Govern de les Illes Balears (IDEIB): Cartografía base e imagen de Mallorca, Menorca, Ibiza y Formentera.",
        "tags": ["baleares", "mallorca", "menorca", "ibiza", "formentera", "ideib", "palma", "mapa"],
        "layers": [("0", "Mapa Base Illes Balears")]
    },
    {
        "id": "suecia_sgu_suelos",
        "name": "Suecia - Suelos y Depósitos Cuaternarios (SGU)",
        "category": "🌲 Medio Ambiente y Naturaleza",
        "region": "Suecia",
        "url": "https://resource.sgu.se/service/wms/130/jordarter-25-100-tusen",
        "default_layer": "JORD_25K_Grundlager",
        "description": "Cartografía oficial de tipos de suelo, sedimentos y depósitos cuaternarios 1:25.000 a 1:100.000 del Servicio Geológico de Suecia (SGU).",
        "tags": ["suecia", "sweden", "suelos", "suelo", "jordarter", "geologia", "sgu", "deposito", "tierra", "edafologia", "sverige"],
        "layers": [
            ("JORD_25K_Grundlager", "Depósitos Cuaternarios / Suelos 25k"),
            ("jord:SE.GOV.SGU.JORD.TACKNINGSKARTA.25K", "Cobertura de Suelos 25k")
        ]
    },
    {
        "id": "suecia_lantmateriet_orto",
        "name": "Suecia - Ortofoto Nacional Oficial (Lantmäteriet)",
        "category": "🛰️ Ortofotos Satelitales y Aéreas",
        "region": "Suecia",
        "url": "https://inspire.lantmateriet.se/inspire-om-wms/service",
        "default_layer": "OI.OrthoimageCoverage",
        "description": "Ortofotografía aérea oficial de alta resolución de toda Suecia certificada por Lantmäteriet (Instituto Geográfico de Suecia).",
        "tags": ["suecia", "sweden", "lantmateriet", "ortofoto", "satelite", "estocolmo", "gotemburgo", "sverige"],
        "layers": [("OI.OrthoimageCoverage", "Ortofoto Nacional de Suecia")]
    },
    {
        "id": "euskadi_ura_hidrologia",
        "name": "País Vasco / URA - Red Hidrográfica, Ríos y Masas de Agua (Agencia Vasca del Agua)",
        "category": "🌊 Aguas, Costas e Inundabilidad",
        "region": "País Vasco (España)",
        "url": "https://www.geo.euskadi.eus/WMS_URA",
        "default_layer": "has_masas_agua_rio_entorno_CAPV_CHE",
        "description": "Cartografía oficial de la red hidrográfica, ríos, cuencas vertientes y masas de agua del País Vasco (URA / GeoEuskadi).",
        "tags": ["euskadi", "pais vasco", "ura", "hidrologia", "rios", "agua", "aguas", "cuencas", "vertientes", "cauces", "geoeuskadi", "araba", "bizkaia", "gipuzkoa"],
        "layers": [
            ("has_masas_agua_rio_entorno_CAPV_CHE", "Ríos y Masas de Agua Superficial"),
            ("has_cuencas_vertientes_a_masas_agua_superficiales", "Cuencas Vertientes"),
            ("has_unidades_hidrologicas", "Unidades Hidrológicas")
        ]
    },
    {
        "id": "espana_mapa_suelos",
        "name": "España - Ocupación del Suelo y Coberturas SIOSE (IGN)",
        "category": "🌲 Medio Ambiente y Naturaleza",
        "region": "España (Nacional)",
        "url": "https://servicios.idee.es/wms-inspire/ocupacion-suelo",
        "default_layer": "LC.LandCoverSurfaces",
        "description": "Ocupación y usos del suelo de España (SIOSE / Corine Land Cover) del Instituto Geográfico Nacional (IGN): clases agrológicas y coberturas de suelo.",
        "tags": ["espana", "suelos", "suelo", "siose", "ocupacion", "corine", "edafologia", "ign", "medio ambiente"],
        "layers": [("LC.LandCoverSurfaces", "Ocupación y Usos del Suelo SIOSE")]
    }
]


# --------------------------------------------------------------------------------------
# 2. MOTOR DE BÚSQUEDA SEMÁNTICA LOCAL INTELIGENTE
# --------------------------------------------------------------------------------------
SPANISH_STOPWORDS = {
    "de", "del", "la", "el", "los", "las", "un", "una", "unos", "unas",
    "y", "e", "o", "u", "a", "al", "en", "para", "por", "con", "sin", "sobre",
    "da", "do", "que", "se", "su", "sus", "es", "son", "como", "me", "te", "mi",
    "tu", "yo", "quiero", "necesito", "busco", "dame", "hay", "tiene", "favor",
    "porfa", "hola", "buenas", "donde", "consigo", "dime", "ver", "cual", "cuales",
    "capa", "capas", "mapa", "mapas", "servicio", "servicios", "wms",
    "archivo", "archivos", "cargado", "cargados", "subido", "subidos",
    "plano", "planos", "proyecto", "proyectos", "zona", "zonas",
    "aqui", "aca", "este", "esta", "estos", "estas",
    "of", "the", "in", "on", "at", "to", "for", "and", "or", "an", "is"
}

SYNONYMS = {
    "ortofoto": [
        "ortofoto", "ortofotos", "ortoimagen", "ortoimagenes", "ortofotografia",
        "satelite", "satelital", "aereo", "pnoa", "ortho", "imagery", "vuelo"
    ],
    "catastro": [
        "catastro", "catastral", "parcela", "parcelas", "linderos", "lote",
        "lotes", "manzana", "manzanas", "inmueble", "finca", "predio", "predios"
    ],
    "curvas": [
        "curvas", "nivel", "topografia", "topografico", "relieve", "elevacion",
        "mdt", "altimetria", "cota", "cotas", "sombreado"
    ],
    "hidrologia": [
        "hidrologia", "hidrologico", "hidrografia", "hidrografico", "agua", "aguas",
        "rio", "rios", "cauce", "cauces", "cuenca", "cuencas", "dph", "drenaje",
        "snczi", "inundable", "inundables", "inundabilidad", "embalse", "ura", "arroyo"
    ],
    "inundable": [
        "inundable", "inundables", "inundacion", "inundaciones", "inundabilidad",
        "snczi", "dph", "cauce", "rio", "retorno", "ramsar"
    ],
    "vias": [
        "vias", "calles", "carreteras", "autopistas", "malla", "vial", "calzada",
        "rutas", "osm", "callejero"
    ],
    "geologia": [
        "geologia", "geologico", "fallas", "rocas", "mineria", "geotecnia", "litologia"
    ],
    "suelos": [
        "suelos", "suelo", "edafologia", "jordarter", "tierra", "geotecnia", "cuaternario",
        "litologia", "pedologia", "agrologico", "siose", "usos del suelo"
    ],
    "medio_ambiente": [
        "medio ambiente", "natura", "red natura", "lic", "zec", "zepa", "enp", "parque",
        "protegido", "montes", "mup", "forestal", "biodiversidad"
    ]
}

GEO_LOCATIONS = {
    "colombia": ["colombia", "bogota", "medellin", "cali", "barranquilla", "cundinamarca", "antioquia", "valle", "igac", "colombiano", "colombiana"],
    "bogota": ["bogota", "cundinamarca", "ideca"],
    "medellin": ["medellin", "antioquia", "geomedellin"],
    "cali": ["cali", "valle", "idecali", "idesc"],
    "mexico": ["mexico", "cdmx", "guadalajara", "monterrey", "inegi", "mexicano", "mexicana"],
    "chile": ["chile", "santiago", "valparaiso", "concepcion", "snit", "mma", "chileno", "chilena"],
    "argentina": ["argentina", "buenos aires", "cordoba", "rosario", "idecor", "argentino", "argentina"],
    "peru": ["peru", "lima", "arequipa", "ingemmet", "geocatmin", "peruano", "peruana"],
    "estados unidos": ["eeuu", "usa", "estados unidos", "usgs", "americano", "americana"],
    "canada": ["canada", "nrcan", "canvec", "canadiense"],
    "suecia": ["suecia", "sweden", "sverige", "sgu", "lantmateriet", "sueco", "sueca", "estocolmo", "gotemburgo", "malmo"],
    "noruega": ["noruega", "norway", "norge", "kartverket", "oslo", "noruego", "noruega"],
    "finlandia": ["finlandia", "finland", "suomi", "maanmittauslaitos", "helsinki", "finlandes"],
    "dinamarca": ["dinamarca", "denmark", "danmark", "copenhague", "danes"],
    "italia": ["italia", "italy", "roma", "milan", "napoles", "turin", "italiano", "italiana"],
    "francia": ["francia", "france", "paris", "geoportail", "frances", "francesa"],
    "alemania": ["alemania", "germany", "berlin", "bkg", "aleman", "alemana"],
    "portugal": ["portugal", "lisboa", "porto", "dgt", "portugues", "portuguesa"],
    "reino unido": ["reino unido", "uk", "inglaterra", "england", "gran bretana", "scotland", "escocia", "londres"],
    "australia": ["australia", "sydney", "melbourne", "australiano", "australiana"],
    "brasil": ["brasil", "brazil", "ibge", "rio", "sao paulo", "brasilia", "brasilero", "brasilera"],
    "japon": ["japon", "japan", "gsi", "tokio", "osaka", "japones", "japonesa"],
    "euskadi": ["euskadi", "pais vasco", "bizkaia", "araba", "alava", "gipuzkoa", "geoeuskadi", "b5m", "donostia", "san sebastian", "bilbao", "vitoria", "vasco", "vasca"],
    "espana": [
        "espana", "spain", "madrid", "cataluna", "barcelona", "andalucia", "sevilla",
        "valencia", "galicia", "navarra", "canarias", "baleares", "espanol", "espanola"
    ],
    "madrid": ["madrid"],
    "andalucia": ["andalucia", "sevilla", "granada", "malaga", "cordoba"],
    "cataluna": ["cataluna", "barcelona", "girona", "tarragona", "lleida", "icgc"],
    "valencia": ["valencia", "alicante", "castellon", "icv"],
    "galicia": ["galicia", "coruna", "pontevedra", "ourense", "lugo", "ideg"],
    "navarra": ["navarra", "idena"],
    "canarias": ["canarias", "tenerife", "palmas", "grafcan"],
    "baleares": ["baleares", "mallorca", "menorca", "ibiza", "ideib"]
}


GEO_CANONICAL_NAMES = {
    "espana": "España",
    "euskadi": "País Vasco",
    "colombia": "Colombia",
    "suecia": "Suecia",
    "australia": "Australia",
    "argentina": "Argentina",
    "mexico": "México",
    "chile": "Chile",
    "peru": "Perú",
    "estados unidos": "Estados Unidos",
    "canada": "Canadá",
    "francia": "Francia",
    "alemania": "Alemania",
    "portugal": "Portugal",
    "reino unido": "Reino Unido",
    "italia": "Italia",
    "noruega": "Noruega",
    "finlandia": "Finlandia",
    "dinamarca": "Dinamarca",
    "brasil": "Brasil",
    "japon": "Japón",
    "madrid": "Madrid",
    "cataluna": "Cataluña",
    "andalucia": "Andalucía",
    "valencia": "Comunidad Valenciana",
    "galicia": "Galicia",
    "navarra": "Navarra",
    "canarias": "Canarias",
    "baleares": "Baleares",
    "bogota": "Bogotá",
    "medellin": "Medellín",
    "cali": "Cali"
}

OFFICIAL_GEOPORTALS: Dict[str, Dict[str, str]] = {
    "australia": {
        "name": "Australia",
        "portal_name": "Geoscience Australia & NationalMap",
        "portal_url": "https://nationalmap.gov.au",
        "description": "Geoportal federal de Australia con servicios WMS de topografía, recursos, costas e hidrología.",
        "search_tips": "En Australia, los servicios WMS estatales más potentes son NSW Spatial Services (Sídney), Vicmap (Victoria) y Qld Spatial (Queensland)."
    },
    "espana": {
        "name": "España",
        "portal_name": "IDEE - Infraestructura de Datos Espaciales de España",
        "portal_url": "https://www.idee.es",
        "description": "Directorio oficial del Consejo Superior Geográfico con más de 3.000 servicios WMS de España.",
        "search_tips": "Puedes consultar la Sede Electrónica del Catastro (DGC) para parcelario rústico/urbano o el IGN para ortofotos PNOA."
    },
    "euskadi": {
        "name": "País Vasco",
        "portal_name": "GeoEuskadi - Infraestructura de Datos Espaciales de Euskadi",
        "portal_url": "https://www.geo.euskadi.eus",
        "description": "Cartografía topográfica, ortofotos de máxima resolución, hidrología (URA) y catastro foral.",
        "search_tips": "En País Vasco, busca los WMS de b5m (Gipuzkoa), Bizkaia o Álava para parcelario y curvas de nivel de 1m."
    },
    "colombia": {
        "name": "Colombia",
        "portal_name": "Geoportal IGAC & Datos Abiertos",
        "portal_url": "https://geoportal.igac.gov.co",
        "description": "Instituto Geográfico Agustín Codazzi (IGAC) y Ministerio de Ambiente (SIAC / IDEAM).",
        "search_tips": "Para Bogotá consulta IDECA (ideca.gov.co) y para geología el SGC (sgc.gov.co)."
    },
    "mexico": {
        "name": "México",
        "portal_name": "INEGI - Instituto Nacional de Estadística y Geografía",
        "portal_url": "https://www.inegi.org.mx/datosabiertos/",
        "description": "Cartografía topográfica, hidrológica, edafológica y catastral de México.",
        "search_tips": "Busca servicios OGC WMS de INEGI o el Geoportal de la Comisión Nacional del Agua (CONAGUA)."
    },
    "estados unidos": {
        "name": "Estados Unidos",
        "portal_name": "USGS The National Map & Data.gov",
        "portal_url": "https://www.usgs.gov/programs/national-geospatial-program/national-map",
        "description": "Servicios WMS oficiales de elevación 3DEP, topografía nacional e hidrografía NHD.",
        "search_tips": "Para límites de propiedad consulta los servidores GIS de cada Condado (County GIS / Property Appraiser)."
    },
    "suecia": {
        "name": "Suecia",
        "portal_name": "Geodataportalen & Lantmäteriet",
        "portal_url": "https://www.geodata.se",
        "description": "Portal nacional de geodatos de Suecia (Lantmäteriet y SGU).",
        "search_tips": "SGU (Sveriges Geologiska Undersökning) ofrece servicios WMS de geología y suelos (jordarter) de libre acceso."
    },
    "argentina": {
        "name": "Argentina",
        "portal_name": "IDERA - Infraestructura de Datos Espaciales de la República Argentina",
        "portal_url": "https://www.idera.gob.ar",
        "description": "Catálogo nacional de capas del IGN Argentina, IDECOR Córdoba, Arba Buenos Aires y Catastro provincial.",
        "search_tips": "Para Córdoba utiliza el geoportal IDECOR (mapascordoba.gob.ar) que publica WMS abiertos."
    },
    "chile": {
        "name": "Chile",
        "portal_name": "IDE Chile - Infraestructura de Datos Geoespaciales",
        "portal_url": "https://www.ide.cl",
        "description": "Geoportal nacional con capas del IGM Chile, Ministerio de Bienes Nacionales y CIREN.",
        "search_tips": "Para recursos hídricos consulta DGA y para catastro el Geoportal del SNIT."
    },
    "peru": {
        "name": "Perú",
        "portal_name": "IDEP & Geocatmin (INGEMMET)",
        "portal_url": "https://geocatmin.ingemmet.gob.pe",
        "description": "Infraestructura de Datos Espaciales del Perú y catastro minero/geológico oficial.",
        "search_tips": "Para topografía nacional consulta IGN Perú y para catastro rural el MINAGRI."
    },
    "francia": {
        "name": "Francia",
        "portal_name": "Géoportail & IGN France",
        "portal_url": "https://www.geoportail.gouv.fr",
        "description": "Institut National de l'Information Géographique et Forestière (IGN) y BRGM.",
        "search_tips": "IGN publica servicios WMS libres de parcelas catastrales (Cadastre) y ortofotos BD ORTHO."
    },
    "alemania": {
        "name": "Alemania",
        "portal_name": "Geoportal Deutschland (BKG)",
        "portal_url": "https://www.geoportal.de",
        "description": "Agencia Federal de Cartografía y Geodesia de Alemania (BKG).",
        "search_tips": "Para catastro inmobiliario busca los servicios ALKIS de cada Bundesland (estado federado)."
    },
    "reino unido": {
        "name": "Reino Unido",
        "portal_name": "data.gov.uk & Ordnance Survey",
        "portal_url": "https://osdatahub.os.uk",
        "description": "Catálogo nacional de geodatos abiertos del gobierno británico y Ordnance Survey.",
        "search_tips": "OS Data Hub ofrece API WMS de mapas topográficos detallados (OS Open Zoomstack)."
    },
    "canada": {
        "name": "Canadá",
        "portal_name": "Natural Resources Canada (GeoGratis / CanVec)",
        "portal_url": "https://maps.canada.ca",
        "description": "Geoportal del gobierno de Canadá con capas topográficas CanVec, hidrología y elevación.",
        "search_tips": "CanVec publica WMS de infraestructura vial, curvas de nivel y masas hídricas."
    },
    "noruega": {
        "name": "Noruega",
        "portal_name": "Kartverket (Geonorge)",
        "portal_url": "https://www.geonorge.no",
        "description": "Portal nacional de geodatos de Noruega (Kartverket) con WMS abiertos de relieve, costa y parcelario.",
        "search_tips": "Geonorge ofrece servicios WMS abiertos de mapas topográficos (Topografisk norgeskart)."
    },
    "finlandia": {
        "name": "Finlandia",
        "portal_name": "Maanmittauslaitos (National Land Survey of Finland)",
        "portal_url": "https://www.maanmittauslaitos.fi/en/e-services/geodata-portal-paikkatietoikkuna",
        "description": "Infraestructura de datos espaciales Paikkatietoikkuna con topografía, parcelas e hidrografía.",
        "search_tips": "Paikkatietoikkuna integra más de 2.000 capas de organismos públicos finlandeses."
    },
    "dinamarca": {
        "name": "Dinamarca",
        "portal_name": "Datafordeler (Klimadatastyrelsen)",
        "portal_url": "https://datafordeler.dk",
        "description": "Plataforma oficial de distribución de datos geoespaciales y cartografía de Dinamarca.",
        "search_tips": "Suministra servicios WMS de ortofotos Skraafoto y modelos digitales del terreno."
    },
    "italia": {
        "name": "Italia",
        "portal_name": "Geoportale Nazionale (Ministero dell'Ambiente)",
        "portal_url": "http://www.pcn.minambiente.it/mattm/",
        "description": "Portal cartográfico nacional de Italia con ortofotos, hidrografía y mapas IGM.",
        "search_tips": "Para catastro inmobiliario regional consulta los geoportales de cada Regione (ej: Regione Lombardia o Lazio)."
    },
    "brasil": {
        "name": "Brasil",
        "portal_name": "INDE - Infraestrutura Nacional de Dados Espaciais (IBGE)",
        "portal_url": "https://visualizador.inde.gov.br",
        "description": "Portal geoespacial del Instituto Brasileiro de Geografia e Estatística (IBGE).",
        "search_tips": "IBGE y ANA (Agência Nacional de Águas) disponen de servicios WMS abiertos para todo Brasil."
    },
    "japon": {
        "name": "Japón",
        "portal_name": "GSI - Geospatial Information Authority of Japan",
        "portal_url": "https://www.gsi.go.jp",
        "description": "Autoridad de Información Geoespacial de Japón con mapas base nacionales y ortofotos.",
        "search_tips": "GSI Maps ofrece servicios de teselas y WMS para proyectos de ingeniería y topografía."
    }
}


def get_canonical_geo_name(geo_key: str) -> str:
    """Devuelve el nombre oficial canónico legible de una clave geográfica."""
    if not geo_key:
        return "esta región"
    norm_k = _normalize_text(geo_key)
    return GEO_CANONICAL_NAMES.get(norm_k, geo_key.capitalize())


def _normalize_text(text: str) -> str:
    """Normaliza texto eliminando acentos, mayúsculas y caracteres especiales."""
    if not text:
        return ""
    t = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode("utf-8").lower()
    return re.sub(r"[^a-z0-9\s]", " ", t)


def _extract_geo_and_thematic(query: str) -> Tuple[Set[str], List[str]]:
    """
    Extrae con precisión entidades geográficas (incluyendo frases compuestas como 'pais vasco',
    'estados unidos', 'buenos aires') y separa los tokens temáticos sustantivos puros (ej: 'hidrologia', 'suelos').
    """
    clean_q = _normalize_text(query)
    detected_geo_keys = set()
    matched_phrases = []

    # Detectar primero frases compuestas ordenando por longitud descendente
    for geo_k, aliases in GEO_LOCATIONS.items():
        all_terms = [geo_k] + aliases
        for term in sorted(all_terms, key=len, reverse=True):
            term_norm = _normalize_text(term)
            pattern = rf"\b{re.escape(term_norm)}\b"
            if re.search(pattern, clean_q):
                detected_geo_keys.add(geo_k)
                detected_geo_keys.update(aliases)
                matched_phrases.append(term_norm)

    # Eliminar las frases geográficas del texto para dejar solo los conceptos temáticos
    remaining_text = clean_q
    for phrase in matched_phrases:
        remaining_text = re.sub(rf"\b{re.escape(phrase)}\b", " ", remaining_text)

    raw_thematic = [w for w in remaining_text.split() if len(w) >= 2]
    thematic_tokens = [w for w in raw_thematic if w not in SPANISH_STOPWORDS]

    return detected_geo_keys, thematic_tokens


CONTEXT_PROJECT_TRIGGERS = {
    "archivo", "archivos", "cargado", "cargados", "subido", "subidos", "plano", "planos",
    "proyecto", "proyectos", "zona", "zonas", "aqui", "aca", "este", "esta", "finca",
    "parcela", "trazado", "actual", "cargada", "subida"
}


def infer_project_geo_keys(
    active_epsg: Optional[Any] = None,
    detected_zone: Optional[Dict[str, Any]] = None,
    uploaded_filename: Optional[str] = None
) -> Set[str]:
    """
    Deduce de forma inteligente el ámbito geográfico del proyecto actual en pantalla
    a partir de la zona detectada por coordenadas, el código EPSG activo o el nombre del archivo.
    """
    geos: Set[str] = set()

    # 1. Por zona geográfica detectada explícitamente en la app (app.py)
    if detected_zone and isinstance(detected_zone, dict):
        z_k = _normalize_text(detected_zone.get("key", ""))
        z_name = _normalize_text(detected_zone.get("name", ""))
        for cand in [z_k, z_name]:
            if not cand:
                continue
            for geo_k, aliases in GEO_LOCATIONS.items():
                if cand == geo_k or cand in aliases:
                    geos.add(geo_k)
                    geos.update(aliases)
            if cand in ["spain", "espana"]:
                geos.add("espana")
                geos.update(GEO_LOCATIONS.get("espana", []))
            elif cand in ["sweden", "suecia"]:
                geos.add("suecia")
                geos.update(GEO_LOCATIONS.get("suecia", []))
            elif cand in ["united states", "usa", "eeuu", "estados unidos"]:
                geos.add("estados unidos")
                geos.update(GEO_LOCATIONS.get("estados unidos", []))

    # 2. Por código EPSG / CRS activo
    if not geos and active_epsg:
        try:
            code_num = int(str(active_epsg).replace("EPSG:", "").strip())
            if code_num in [25828, 25829, 25830, 25831, 25832, 23028, 23029, 23030, 23031, 4258, 4230]:
                geos.add("espana")
                geos.update(GEO_LOCATIONS.get("espana", []))
            elif code_num in [3116, 9377]:
                geos.add("colombia")
                geos.update(GEO_LOCATIONS.get("colombia", []))
            elif 3006 <= code_num <= 3018:
                geos.add("suecia")
                geos.update(GEO_LOCATIONS.get("suecia", []))
            elif code_num in [5343, 5344, 5345, 5346, 5347, 5348, 5349, 22181, 22182, 22183, 22184, 22185]:
                geos.add("argentina")
                geos.update(GEO_LOCATIONS.get("argentina", []))
            elif (32610 <= code_num <= 32619) or (2225 <= code_num <= 2286):
                geos.add("estados unidos")
                geos.update(GEO_LOCATIONS.get("estados unidos", []))
        except Exception:
            pass

    # 3. Refinamiento autonómico por nombre del archivo cargado (ej: bilbao_parcela.dxf)
    if uploaded_filename:
        f_norm = _normalize_text(uploaded_filename)
        for term, sub_geo in [
            ("euskadi", "euskadi"), ("vasco", "euskadi"), ("bizkaia", "euskadi"),
            ("araba", "euskadi"), ("alava", "euskadi"), ("gipuzkoa", "euskadi"),
            ("bilbao", "euskadi"), ("donostia", "euskadi"), ("vitoria", "euskadi"),
            ("madrid", "madrid"), ("cataluna", "cataluna"), ("barcelona", "cataluna"),
            ("andalucia", "andalucia"), ("galicia", "galicia"), ("valencia", "valencia")
        ]:
            if re.search(rf"\b{term}\b", f_norm):
                geos = {sub_geo}
                geos.update(GEO_LOCATIONS.get(sub_geo, []))
                break

    return geos


def _detect_query_geo(query: str) -> List[str]:
    """Detecta las claves geográficas principales canónicas mencionadas en la consulta."""
    clean_q = _normalize_text(query)
    detected_primary_keys = []
    for geo_k, aliases in GEO_LOCATIONS.items():
        all_terms = [geo_k] + aliases
        for term in sorted(all_terms, key=len, reverse=True):
            term_norm = _normalize_text(term)
            pattern = rf"\b{re.escape(term_norm)}\b"
            if re.search(pattern, clean_q):
                if geo_k not in detected_primary_keys:
                    detected_primary_keys.append(geo_k)
                break
    return detected_primary_keys


def search_wms_catalog(
    query: str,
    category_filter: Optional[str] = None,
    region_filter: Optional[str] = None,
    project_geo_fallback: Optional[Set[str]] = None
) -> List[Dict[str, Any]]:
    """
    Buscador determinista, de alta precisión y sin alucinaciones.
    1. Si se menciona una región (ej: 'pais vasco', 'suecia'), descarta cualquier servicio de otra región.
    2. Si se menciona un tema (ej: 'hidrologia', 'suelos'), exige coincidencia a nivel de palabra completa (evita que 'rio' coincida con 'parcelario').
    3. Si el usuario refiere a su proyecto ('archivo cargado', 'mi plano', etc.) o no indica país, hereda automáticamente la región geográfica del proyecto.
    4. Devuelve únicamente los servicios oficiales verificados que coinciden.
    """
    clean_q = _normalize_text(query)
    q_words = set(clean_q.split())
    query_geo_keys, thematic_tokens = _extract_geo_and_thematic(query)

    # Detección contextual:
    # Solo se restringe a project_geo_fallback si el usuario explícitamente se refirió a su plano/archivo
    # (ej: 'archivo cargado', 'mi plano', 'mi proyecto', 'mi zona').
    # Si la búsqueda es temática general (ej: 'curvas de nivel', 'catastro', 'ortofoto'), se busca en todo
    # el catálogo y solo se prioriza con un bono de puntuación la zona del proyecto.
    has_context_intent = bool(q_words.intersection(CONTEXT_PROJECT_TRIGGERS))
    if has_context_intent and project_geo_fallback:
        query_geo_keys = set(project_geo_fallback)

    if category_filter and category_filter == "Todas las categorías":
        category_filter = None
    if region_filter and region_filter == "Todas las regiones":
        region_filter = None

    scored_results = []
    for item in WMS_DATABASE:
        if category_filter and item["category"] != category_filter:
            continue

        if region_filter and region_filter.lower() not in item["region"].lower():
            continue

        item_name = _normalize_text(item["name"])
        item_reg = _normalize_text(item["region"])
        item_desc = _normalize_text(item["description"])
        item_tags = [_normalize_text(t) for t in item.get("tags", [])]

        # Conjunto de palabras completas para evitar colisiones de subcadenas (ej: 'rio' en 'parcelario')
        item_words = set(item_name.split() + item_desc.split() + item_tags)

        # REGLA ESTRICTA 1: COHERENCIA GEOGRÁFICA
        if query_geo_keys:
            item_matches_geo = any(g in item_reg or g in item_name or g in item_tags for g in query_geo_keys)
            if not item_matches_geo:
                continue

        # REGLA ESTRICTA 2: COHERENCIA TEMÁTICA
        # Si el usuario especificó una temática (ej: 'hidrologia', 'suelos', 'catastro'),
        # el servicio DEBE coincidir con al menos un término temático a nivel de palabra completa.
        if thematic_tokens:
            has_thematic_match = False
            for t_tok in thematic_tokens:
                syns = [t_tok]
                for sk, sl in SYNONYMS.items():
                    if t_tok == sk or t_tok in sl:
                        syns.extend(sl)
                syn_set = set(syns)
                if syn_set.intersection(item_words):
                    has_thematic_match = True
                    break
            if not has_thematic_match:
                continue

        # Puntuación
        score = 0
        matched_tokens_count = 0
        all_tokens = list(query_geo_keys) + thematic_tokens if query_geo_keys else thematic_tokens

        for tok in thematic_tokens:
            syns = [tok]
            for syn_key, syn_list in SYNONYMS.items():
                if tok == syn_key or tok in syn_list:
                    syns.extend(syn_list)
            syns_set = set(syns)

            if syns_set.intersection(set(item_tags)):
                score += 40
                matched_tokens_count += 1
            elif syns_set.intersection(set(item_name.split())):
                score += 35
                matched_tokens_count += 1
            elif syns_set.intersection(set(item_desc.split())):
                score += 20
                matched_tokens_count += 1

        # Bonificación a coincidencia exacta de región
        if query_geo_keys:
            if any(g in item_reg for g in query_geo_keys):
                score += 60
        elif project_geo_fallback:
            # Si es búsqueda general, priorizar en el listado las capas de la zona del proyecto
            if any(g in item_reg or g in item_name or g in item_tags for g in project_geo_fallback):
                score += 45

        if thematic_tokens:
            coverage_ratio = matched_tokens_count / max(len(thematic_tokens), 1)
            if coverage_ratio >= 1.0:
                score += 100

        scored_results.append((score, item))

    scored_results.sort(key=lambda x: x[0], reverse=True)

    if scored_results:
        top_score = scored_results[0][0]
        min_threshold = max(top_score * 0.5, 30)
        filtered = [item for sc, item in scored_results if sc >= min_threshold]
        return filtered[:10]

    return []


def build_smart_offline_response(
    query: str,
    detected_geos: List[str],
    zone_disp: Optional[str] = None,
    is_context_q: bool = False
) -> str:
    """
    Construye una respuesta técnica, realista y orientada a la ingeniería para el modo sin API.
    En lugar de dar un mensaje de error genérico, proporciona enlaces directos a Google con sintaxis
    GIS WMS, enlaces al Geoportal oficial nacional y recomendaciones para cargarlo con el Inspector WMS.
    """
    target_k = detected_geos[0] if detected_geos else None
    target_name = get_canonical_geo_name(target_k) if target_k else (zone_disp or "esta región")

    # Construcción de consulta optimizada para Google Dorks (WMS / GetCapabilities)
    clean_q = _normalize_text(query)
    q_words = [w for w in clean_q.split() if w not in SPANISH_STOPWORDS]
    thematic_str = " ".join(q_words) if q_words else query

    norm_target = _normalize_text(target_name)
    geo_tokens = set()
    if detected_geos:
        for g in detected_geos:
            geo_tokens.add(g)
            for term in GEO_LOCATIONS.get(g, []):
                geo_tokens.update(_normalize_text(term).split())
    if norm_target and norm_target != "esta region":
        geo_tokens.update(norm_target.split())

    thematic_only_words = [w for w in q_words if w not in geo_tokens]
    thematic_clean_str = " ".join(thematic_only_words) if thematic_only_words else thematic_str

    if norm_target in clean_q or not target_k:
        google_query_term = f"{query} WMS GetCapabilities service"
    else:
        google_query_term = f"{target_name} {thematic_clean_str} WMS GetCapabilities service"

    encoded_google_q = urllib.parse.quote_plus(google_query_term)
    google_search_url = f"https://www.google.com/search?q={encoded_google_q}"

    # Geoportal oficial si existe
    portal = OFFICIAL_GEOPORTALS.get(target_k) if target_k else None

    # Búsqueda de alternativas temáticas en el catálogo local
    global_alternatives = search_wms_catalog(thematic_str, project_geo_fallback=None) if thematic_str else []

    lines = [
        f"### 🌐 Localizador Cartográfico Oficial: **{target_name}**\n",
        f"Actualmente en la base de datos local no dispongo de la URL precargada para **'{query}'** en **{target_name}**, pero puedes obtener el servidor oficial en segundos con estos recursos directos:\n",
        f"#### 1. 🔍 Búsqueda directa del servidor WMS en Google",
        f"Haz clic en este enlace preparado técnicamente para localizar el endpoint WMS oficial en Google:",
        f"👉 **[🔗 Buscar '{google_query_term}' en Google]({google_search_url})**\n"
    ]

    if portal:
        lines.append(f"#### 2. 🏛️ Geoportal Nacional Oficial ({portal['portal_name']})")
        lines.append(f"- **Web:** [{portal['portal_url']}]({portal['portal_url']})")
        lines.append(f"- **Ámbito:** {portal['description']}")
        lines.append(f"- 💡 **Tip para AutoCAD:** {portal['search_tips']}\n")

    lines.append("#### 3. ⚡ ¿Cómo insertarlo en tu plano CAD?")
    lines.append("1. Copia la URL del servicio WMS que encuentres en Google o en el Geoportal (la que contiene `.../wms` o `.../WMSServer`).")
    lines.append("2. Dirígete a la pestaña de arriba: **'🔍 Inspeccionar URL Externa (GetCapabilities)'**.")
    lines.append("3. Pega la URL y pulsa **'Inspeccionar Servidor en Vivo'**: el sistema leerá automáticamente todas las capas publicadas por la entidad y te creará el botón interactivo para descargarlo e insertarlo en AutoCAD con archivo `.tfw` georreferenciado.\n")

    lines.append("---")
    lines.append("💡 **Sobre el uso de IA (¡Es 100% GRATIS, no necesitas cuenta de pago!):**")
    lines.append("No requieres ninguna cuenta de pago ni tarjeta bancaria para usar IA en este asistente:")
    lines.append("- **Google Gemini:** Es **100% gratuito** con tu cuenta de Gmail en [Google AI Studio](https://aistudio.google.com/) (generas tu API Key en 30 segundos sin tarjeta bancaria).")
    lines.append("- **Groq Cloud:** Es **100% gratuito** y ultra-rápido en [console.groq.com](https://console.groq.com/) (modelos Llama-3 de código abierto sin tarjeta).")
    lines.append("Con cualquiera de las dos, el asistente busca e inserta los WMS mundiales automáticamente sin coste alguno.")

    if global_alternatives:
        lines.append("\n---\n📚 **Capas oficiales verificadas de esta temática disponibles en otros ámbitos como referencia:**\n")
        for m in global_alternatives[:3]:
            lines.append(f"### {m['name']}")
            lines.append(f"- **Ámbito:** {m['region']} | **Categoría:** {m['category']}")
            lines.append(f"- **Descripción:** {m['description']}")
            lines.append(f"- **URL Base:** `{m['url']}`")
            lines.append(f"- **Capa recomendada:** `{m['default_layer']}`")
            lines.append(f"[APPLY_WMS: {json.dumps({'name': m['name'], 'url': m['url'], 'layer': m['default_layer']})}]\n")

    return "\n".join(lines)


# --------------------------------------------------------------------------------------
# 3. INSPECTOR EN VIVO DE CAPAS WMS (GETCAPABILITIES)
# --------------------------------------------------------------------------------------
def inspect_wms_live(url: str) -> Dict[str, Any]:
    """
    Inspecciona en tiempo real cualquier URL de servidor WMS mediante GetCapabilities.
    Incluye diagnóstico inteligente para URLs desactualizadas, migradas o raíces de ArcGIS.
    """
    clean_url = url.split("?")[0].strip()
    if not clean_url or not clean_url.startswith("http"):
        return {"success": False, "error": "URL no válida. Debe comenzar con http:// o https://"}

    parsed = urllib.parse.urlparse(clean_url)
    host = parsed.netloc

    # Comprobación de URL raíz de ArcGIS (muy común pegar la raíz /arcgis/services/ en vez del MapServer)
    clean_low = clean_url.lower()
    is_arcgis_root = any(p in clean_low for p in ["/arcgis/services", "/server/services", "/arcgis/rest", "/server/rest"]) and "wmsserver" not in clean_low and "mapserver" not in clean_low

    migrated_domains = {
        "maps.six.nsw.gov.au": {
            "new_domain": "portal.spatial.nsw.gov.au",
            "desc": "Spatial Services NSW ha migrado progresivamente sus servicios del antiguo SIX Maps al nuevo Spatial Collaboration Portal.",
            "example": "https://portal.spatial.nsw.gov.au/server/services/Cadastre_History/MapServer/WMSServer"
        }
    }

    if is_arcgis_root:
        dork_q = f"site:{host} WMSServer OR GetCapabilities"
        dork_url = f"https://www.google.com/search?q={urllib.parse.quote_plus(dork_q)}"
        mig_info = migrated_domains.get(host.lower(), {})
        mig_msg = f"\n\n💡 **Nota de migración:** {mig_info.get('desc')} (Ejemplo activo: `{mig_info.get('example')}`)." if mig_info else ""
        return {
            "success": False,
            "error": (
                f"⚠️ Has introducido la dirección raíz de un servidor ArcGIS (`{clean_url}`).\n\n"
                "Un servicio WMS de ArcGIS no puede ser la raíz, debe apuntar a un servicio específico y terminar en `/MapServer/WMSServer` "
                f"(por ejemplo: `{clean_url.rstrip('/')}/NombreCapa/MapServer/WMSServer`).{mig_msg}\n\n"
                f"👉 **[🔗 Buscar servicios WMS activos de {host} en Google]({dork_url})**"
            )
        }

    try:
        resp = requests.get(
            clean_url,
            params={"SERVICE": "WMS", "REQUEST": "GetCapabilities"},
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                "Accept": "text/xml,application/xml,application/xhtml+xml,text/html;q=0.9,*/*;q=0.8"
            },
            timeout=10,
            verify=False
        )
        if resp.status_code != 200:
            dork_q = f"{host} WMS GetCapabilities service"
            dork_url = f"https://www.google.com/search?q={urllib.parse.quote_plus(dork_q)}"
            mig_info = migrated_domains.get(host.lower(), {})
            mig_msg = f"\n\n💡 **Nota de migración:** {mig_info.get('desc')} (Ejemplo: `{mig_info.get('example')}`)." if mig_info else ""
            return {
                "success": False,
                "error": (
                    f"El servidor respondió con código HTTP {resp.status_code}. Es muy probable que el enlace esté desactualizado o fuera de servicio.{mig_msg}\n\n"
                    f"👉 **[🔗 Localizar enlace WMS actualizado en Google]({dork_url})**"
                )
            }

        # Si el servidor devolvió HTML en vez de XML (por ejemplo página de error de ArcGIS o Apache)
        content_type = resp.headers.get("Content-Type", "").lower()
        if "html" in content_type and not resp.content.strip().startswith(b"<?xml"):
            dork_q = f"site:{host} WMSServer OR GetCapabilities"
            dork_url = f"https://www.google.com/search?q={urllib.parse.quote_plus(dork_q)}"
            return {
                "success": False,
                "error": (
                    f"El servidor no devolvió un documento XML OGC WMS (devolvió una página web HTML con código {resp.status_code}). "
                    "Verifica que la URL sea un endpoint WMS válido terminado en `/WMSServer` o `/wms`.\n\n"
                    f"👉 **[🔗 Buscar servicios WMS activos de {host} en Google]({dork_url})**"
                )
            }

        root = ET.fromstring(resp.content)
        title = "Servidor WMS"
        abstract = ""
        service_el = root.find("{*}Service")
        if service_el is not None:
            t_el = service_el.find("{*}Title")
            if t_el is not None and t_el.text:
                title = t_el.text.strip()
            a_el = service_el.find("{*}Abstract")
            if a_el is not None and a_el.text:
                abstract = a_el.text.strip()

        layers = []
        crs_set = set()
        for el in root.iter():
            tag = el.tag.split("}")[-1] if "}" in el.tag else el.tag
            if tag.lower() in ("crs", "srs") and el.text:
                val = el.text.strip().upper()
                if "EPSG:" in val:
                    crs_set.add(val)
            elif tag == "Layer":
                name_el = el.find("{*}Name")
                title_el = el.find("{*}Title")
                if name_el is not None and name_el.text:
                    n = name_el.text.strip()
                    t = title_el.text.strip() if (title_el is not None and title_el.text) else n
                    if not n.startswith("<![CDATA") and n.upper() != "WMS":
                        if not any(x["name"] == n for x in layers):
                            layers.append({"name": n, "title": t})

        return {
            "success": True,
            "title": title,
            "abstract": abstract,
            "layers": layers,
            "supported_crs": sorted(list(crs_set))[:20],
            "url": clean_url
        }
    except requests.exceptions.Timeout:
        return {"success": False, "error": "Tiempo de espera agotado al conectar con el servidor WMS (Timeout)."}
    except requests.exceptions.SSLError:
        return {"success": False, "error": "Error de certificado SSL en el servidor WMS."}
    except Exception as e:
        return {"success": False, "error": f"Error al procesar GetCapabilities: {str(e)}"}


# --------------------------------------------------------------------------------------
# 4. CLIENTE DE IA UNIVERSAL (OPENAI, ANTHROPIC CLAUDE, GEMINI, GROQ, DEEPSEEK, OPENROUTER, ETC.)
# --------------------------------------------------------------------------------------
# Catálogo base por defecto (se auto-actualiza dinámicamente en tiempo real con la API en vivo de cada proveedor)
PROVIDER_MODELS_CATALOG = {
    "gemini": [
        "gemini-3.8-flash",
        "gemini-3.6-flash",
        "gemini-3.5-flash-lite",
        "gemini-3.1-pro-preview",
        "gemini-4-argon",
    ],
    "openai": [
        "gpt-5",
        "gpt-4.5",
        "gpt-4o",
        "gpt-4o-mini",
        "o3",
        "o3-mini",
        "o1",
    ],
    "anthropic": [
        "claude-3-7-sonnet-20250219",
        "claude-3-5-sonnet-20241022",
        "claude-3-5-haiku-20241022",
        "claude-3-opus-20240229",
    ],
    "groq": [
        "llama-3.3-70b-versatile",
        "deepseek-r1-distill-qwen-32b",
        "qwen-2.5-32b",
        "qwen-2.5-coder-32b",
        "llama-3.1-8b-instant",
    ],
    "deepseek": [
        "deepseek-chat",
        "deepseek-reasoner",
    ],
    "openrouter": [
        "anthropic/claude-3.7-sonnet",
        "google/gemini-3.8-flash",
        "deepseek/deepseek-r1",
        "meta-llama/llama-3.3-70b-instruct",
    ],
    "mistral": [
        "mistral-small-latest",
        "mistral-large-latest",
        "codestral-latest",
    ],
    "perplexity": [
        "sonar",
        "sonar-pro",
    ],
    "custom": [
        "llama3.3",
        "deepseek-r1",
        "mistral",
        "qwen2.5",
    ]
}


def detect_ai_provider(api_key: str, user_selected: str = "auto") -> str:
    """
    Detecta automáticamente o respeta la selección manual del usuario para el proveedor de IA.
    Soporta:
      - 'openai': OpenAI ChatGPT (sk-..., sk-proj-...)
      - 'anthropic': Anthropic Claude (sk-ant-...)
      - 'gemini': Google Gemini (AIzaSy...)
      - 'openrouter': OpenRouter (sk-or-...)
      - 'groq': Groq (gsk_...)
      - 'perplexity': Perplexity AI (pplx-...)
      - 'deepseek': DeepSeek (sk-...)
      - 'mistral': Mistral AI
      - 'custom': Servidor Local o Personalizado (Ollama, LM Studio, vLLM, etc.)
    """
    if user_selected and user_selected != "auto":
        return user_selected

    k = api_key.strip() if api_key else ""
    if not k:
        return "none"

    k_lower = k.lower()
    if k_lower.startswith("sk-ant-"):
        return "anthropic"
    elif k_lower.startswith("sk-or-"):
        return "openrouter"
    elif k_lower.startswith("gsk_"):
        return "groq"
    elif k_lower.startswith("pplx-"):
        return "perplexity"
    elif k_lower.startswith("aiza"):
        return "gemini"
    elif k_lower.startswith("sk-"):
        return "openai"

    return "openai"


def discover_available_gemini_models(api_key: str, force_refresh: bool = False) -> Tuple[List[str], Optional[str]]:
    """
    Descubre dinámicamente en tiempo real TODOS los modelos vigentes disponibles para la clave API en Google AI Studio.
    Se auto-actualiza automáticamente cada vez que Google lanza nuevos modelos (Gemini 2.5, 3.x, 4, etc.).
    """
    if not api_key or not api_key.strip():
        return [], "Clave vacía"

    clean_key = api_key.strip()
    if clean_key.lower().startswith("sk-") or clean_key.lower().startswith("gsk_") or clean_key.lower().startswith("pplx-"):
        return [], None

    cached_key = st.session_state.get("_cached_gemini_api_key")
    cached_models = st.session_state.get("_cached_gemini_models")
    if not force_refresh and cached_key == clean_key and cached_models:
        # Invalidar caché si contenía modelos antiguos descontinuados (ej: 2.5, 1.5)
        if not any(any(old in str(m).lower() for old in ["2.5", "2.0", "1.5", "1.0"]) for m in cached_models):
            return cached_models, None

    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models?key={clean_key}"
        resp = requests.get(url, timeout=7)
        if resp.status_code == 200:
            data = resp.json()
            models_found = []
            for m in data.get("models", []):
                methods = m.get("supportedGenerationMethods", [])
                if "generateContent" in methods:
                    name = m.get("name", "")
                    clean_name = name.replace("models/", "").strip()
                    clean_low = clean_name.lower()
                    if any(x in clean_low for x in ["embedding", "imagen", "aqa", "realtime", "tts"]):
                        continue
                    if "gemini" in clean_low:
                        models_found.append(clean_name)

            if models_found:
                # Asegurar presencia del modelo insignia actual gemini-3.8-flash
                if "gemini-3.8-flash" not in models_found:
                    models_found.append("gemini-3.8-flash")

                # Purgar modelos descontinuados de la API de Google AI Studio (2.5, 2.0, 1.5, 1.0)
                modern_models = [m for m in models_found if not any(old in m.lower() for old in ["2.5", "2.0", "1.5", "1.0"])]
                if modern_models:
                    models_found = modern_models

                def _version_score(name: str) -> float:
                    n = name.lower()
                    if "gemini-3.8-flash" in n:
                        return 100.0
                    if any(old in n for old in ["2.5", "2.0", "1.5", "1.0"]):
                        return -100.0
                    score = 0.0
                    match = re.search(r"gemini-(\d+(?:\.\d+)?)", n)
                    if match:
                        try:
                            score = float(match.group(1)) * 10.0
                        except Exception:
                            score = 10.0
                    if "flash" in n and "lite" not in n:
                        score += 0.5
                    elif "flash-lite" in n or "lite" in n:
                        score += 0.4
                    elif "pro" in n or "argon" in n:
                        score += 0.2
                    if "exp" in n or "preview" in n:
                        score -= 0.1
                    return score

                models_found.sort(key=_version_score, reverse=True)

                seen = set()
                unique_models = []
                for m in models_found:
                    if m not in seen:
                        seen.add(m)
                        unique_models.append(m)

                st.session_state["_cached_gemini_api_key"] = clean_key
                st.session_state["_cached_gemini_models"] = unique_models
                return unique_models, None
        elif resp.status_code == 400:
            err_data = resp.json().get("error", {})
            msg = err_data.get("message", "")
            if "API key not valid" in msg or "INVALID_ARGUMENT" in err_data.get("status", ""):
                return [], "❌ La clave de API introducida no es válida para Google Gemini. Cópiala directamente desde Google AI Studio (aistudio.google.com)."
        elif resp.status_code == 403:
            return [], "❌ La clave de API no tiene permisos para Generative Language o tiene restricciones en Google Cloud Console."
    except Exception:
        pass

    fallback = [
        "gemini-3.8-flash",
        "gemini-3.6-flash",
        "gemini-3.5-flash-lite",
        "gemini-3.1-pro-preview",
        "gemini-4-argon",
    ]
    return fallback, None


def discover_available_openai_models(api_key: str, force_refresh: bool = False) -> List[str]:
    """Descubre dinámicamente los modelos vigentes a los que tiene acceso la clave API de OpenAI."""
    if not api_key or not api_key.strip():
        return []
    clean_key = api_key.strip()
    if not clean_key.startswith("sk-") or clean_key.startswith("sk-ant-") or clean_key.startswith("sk-or-"):
        return []

    cached_key = st.session_state.get("_cached_openai_api_key")
    cached_models = st.session_state.get("_cached_openai_models")
    if not force_refresh and cached_key == clean_key and cached_models:
        return cached_models

    try:
        resp = requests.get(
            "https://api.openai.com/v1/models",
            headers={"Authorization": f"Bearer {clean_key}"},
            timeout=4
        )
        if resp.status_code == 200:
            data = resp.json()
            models_list = [m["id"] for m in data.get("data", []) if "id" in m]
            valid_chat = []
            for m in models_list:
                m_low = m.lower()
                if any(x in m_low for x in ["gpt-3.5", "gpt-4-03", "gpt-4-06", "audio", "realtime", "transcribe", "tts", "embedding", "moderation", "instruct", "search", "dall-e"]):
                    continue
                if any(x in m_low for x in ["gpt-4", "gpt-5", "o1", "o2", "o3", "o4", "chatgpt"]):
                    valid_chat.append(m)

            def _rank_openai(name: str) -> float:
                n = name.lower()
                score = 0.0
                match = re.search(r"(?:gpt-|o)(\d+(?:\.\d+)?)", n)
                if match:
                    try:
                        score = float(match.group(1)) * 10.0
                    except Exception:
                        score = 10.0
                if "mini" in n:
                    score += 0.5
                return score

            valid_chat.sort(key=_rank_openai, reverse=True)
            if valid_chat:
                st.session_state["_cached_openai_api_key"] = clean_key
                st.session_state["_cached_openai_models"] = valid_chat
                return valid_chat
    except Exception:
        pass

    return []


def discover_provider_models(
    provider: str,
    api_key: str,
    custom_url: Optional[str] = None,
    force_refresh: bool = False
) -> List[str]:
    """
    Descubre dinámicamente en tiempo real los modelos vigentes para CUALQUIER proveedor del mundo:
    - Google Gemini (v1beta/models)
    - OpenAI (v1/models)
    - Anthropic Claude (v1/models)
    - Groq (openai/v1/models)
    - DeepSeek (models)
    - OpenRouter (api/v1/models)
    - Mistral AI (v1/models)
    - Servidor Local / Ollama / LM Studio (/models o /api/tags)
    """
    clean_key = api_key.strip() if api_key else ""
    cache_key = f"_cached_models_{provider}_{clean_key[:12] if clean_key else 'nokey'}"
    
    if not force_refresh:
        cached = st.session_state.get(cache_key)
        if cached:
            if provider == "gemini" and any(any(old in str(m).lower() for old in ["2.5", "2.0", "1.5", "1.0"]) for m in cached):
                pass
            else:
                return cached

    models_found = []

    # 1. Google Gemini
    if provider == "gemini":
        gem_models, _ = discover_available_gemini_models(clean_key, force_refresh=force_refresh)
        if gem_models:
            models_found = gem_models

    # 2. OpenAI
    elif provider == "openai":
        openai_models = discover_available_openai_models(clean_key, force_refresh=force_refresh)
        if openai_models:
            models_found = openai_models

    # 3. Anthropic Claude
    elif provider == "anthropic" and clean_key:
        try:
            resp = requests.get(
                "https://api.anthropic.com/v1/models",
                headers={
                    "x-api-key": clean_key,
                    "anthropic-version": "2023-06-01"
                },
                timeout=4
            )
            if resp.status_code == 200:
                data = resp.json()
                for m in data.get("data", []):
                    m_id = m.get("id", "")
                    if m_id and "claude" in m_id.lower():
                        models_found.append(m_id)
        except Exception:
            pass

    # 4. Groq
    elif provider == "groq" and clean_key:
        try:
            resp = requests.get(
                "https://api.groq.com/openai/v1/models",
                headers={"Authorization": f"Bearer {clean_key}"},
                timeout=4
            )
            if resp.status_code == 200:
                data = resp.json()
                for m in data.get("data", []):
                    m_id = m.get("id", "")
                    m_low = m_id.lower()
                    if any(x in m_low for x in ["whisper", "audio", "guard", "embedding"]):
                        continue
                    if m_id:
                        models_found.append(m_id)
        except Exception:
            pass

    # 5. DeepSeek
    elif provider == "deepseek" and clean_key:
        try:
            resp = requests.get(
                "https://api.deepseek.com/models",
                headers={"Authorization": f"Bearer {clean_key}"},
                timeout=4
            )
            if resp.status_code == 200:
                data = resp.json()
                for m in data.get("data", []):
                    m_id = m.get("id", "")
                    if m_id:
                        models_found.append(m_id)
        except Exception:
            pass

    # 6. OpenRouter
    elif provider == "openrouter":
        try:
            headers = {"Authorization": f"Bearer {clean_key}"} if clean_key else {}
            resp = requests.get("https://openrouter.ai/api/v1/models", headers=headers, timeout=4)
            if resp.status_code == 200:
                data = resp.json()
                for m in data.get("data", []):
                    m_id = m.get("id", "")
                    m_low = m_id.lower()
                    if any(x in m_low for x in ["embed", "image", "audio", "vision-only"]):
                        continue
                    if any(x in m_low for x in ["llama-3", "claude-3", "deepseek", "gemini", "qwen", "mistral"]):
                        models_found.append(m_id)
                    if len(models_found) >= 30:
                        break
        except Exception:
            pass

    # 7. Mistral AI
    elif provider == "mistral" and clean_key:
        try:
            resp = requests.get(
                "https://api.mistral.ai/v1/models",
                headers={"Authorization": f"Bearer {clean_key}"},
                timeout=4
            )
            if resp.status_code == 200:
                data = resp.json()
                for m in data.get("data", []):
                    m_id = m.get("id", "")
                    m_low = m_id.lower()
                    if any(x in m_low for x in ["embed", "moderation"]):
                        continue
                    if m_id:
                        models_found.append(m_id)
        except Exception:
            pass

    # 8. Servidor Local / Ollama / LM Studio
    elif provider == "custom":
        url = custom_url.strip() if custom_url and custom_url.strip() else "http://localhost:11434"
        clean_base = url.rstrip("/")
        tested_endpoints = [
            f"{clean_base}/models" if not clean_base.endswith("/v1") else f"{clean_base}/models",
            f"{clean_base}/v1/models",
            f"{clean_base}/api/tags"
        ]
        headers = {"Authorization": f"Bearer {clean_key}"} if clean_key else {}
        for ep in tested_endpoints:
            try:
                resp = requests.get(ep, headers=headers, timeout=2.5)
                if resp.status_code == 200:
                    data = resp.json()
                    if "data" in data and isinstance(data["data"], list):
                        for m in data["data"]:
                            m_id = m.get("id", "")
                            if m_id:
                                models_found.append(m_id)
                        if models_found:
                            break
                    elif "models" in data and isinstance(data["models"], list):
                        for m in data["models"]:
                            m_name = m.get("name", "")
                            if m_name:
                                models_found.append(m_name)
                        if models_found:
                            break
            except Exception:
                pass

    if models_found:
        seen = set()
        unique = []
        for m in models_found:
            if m not in seen:
                seen.add(m)
                unique.append(m)
        st.session_state[cache_key] = unique
        return unique

    return list(PROVIDER_MODELS_CATALOG.get(provider, ["default"]))


def _build_wms_system_instruction(context_info: Optional[Dict[str, Any]] = None) -> str:
    """Genera la instrucción del sistema experta en WMS y CAD compartida para todos los proveedores de IA."""
    catalog_summary = []
    for item in WMS_DATABASE[:40]:
        catalog_summary.append(
            f"- {item['name']} ({item['region']}): URL={item['url']} | Capa={item['default_layer']} | {item['description']}"
        )
    catalog_text = "\n".join(catalog_summary)

    ctx_str = ""
    if context_info:
        ctx_str = (
            f"\nCONTEXTO DEL PROYECTO ACTUAL DEL USUARIO EN LA PANTALLA:\n"
            f"- Proyección cartográfica configurada: EPSG:{context_info.get('active_epsg', '25830')}\n"
            f"- Archivo cargado en la app: {context_info.get('uploaded_filename', 'Ninguno')}\n"
            f"- Zona / País detectado del proyecto: {context_info.get('detected_zone', 'Deducir de EPSG o archivo')}\n"
            f"- Servicio cartográfico actualmente seleccionado: {context_info.get('current_service', 'Ortofoto PNOA')}\n"
            f"REGLA DE CONTEXTO: Si el usuario dice 'mi archivo', 'archivo cargado', 'mi plano' o 'mi proyecto', o si solicita una capa temática (ej: hidrología, suelos, catastro) sin especificar país, ASUME que se refiere a la ubicación de su archivo cargado y a su CRS/EPSG actual, recomendándole la capa oficial de esa zona geográfica concreta.\n"
        )

    system_instruction = f"""
Eres 'WMS Assistant Worldwide', un Ingeniero Especialista Senior en Sistemas de Información Geográfica (SIG), Cartografía Oficial Mundial (España, Europa, Latinoamérica, EE.UU., Canadá, Australia y Global) y proyectos en AutoCAD, AutoCAD Map 3D y Civil 3D.
Tu objetivo es ayudar al usuario a encontrar las URLs y capas exactas de servicios WMS (Web Map Service) para insertar ortofotos y mapas en su plano CAD.

{ctx_str}

Dispones de este catálogo verificado de referencia:
{catalog_text}

INSTRUCCIONES CLAVE Y REGLAS DE CONFIABILIDAD DE URLS:
1. Responde de forma concisa, técnica y cordial en español.
2. Tu alcance es MUNDIAL. Si el usuario pregunta por España, Colombia, México, Chile, Perú, EE.UU., Francia, Alemania o cualquier otro país, oriéntalo con el servicio oficial o regional correspondiente.
3. SIEMPRE que recomiendes un servicio WMS concreto que el usuario pueda usar, incluye al final un bloque especial con este formato exacto para que la interfaz cree un botón de carga rápida con 1 clic:
   [APPLY_WMS: {{"name": "Nombre descriptivo", "url": "https://url-del-servicio...", "layer": "nombre_capa"}}]
4. REGLA ESTRICTA DE URLS OFICIALES:
   - Para Colombia IGAC: Utiliza SIEMPRE 'https://mapas2.igac.gov.co/server/services/carto/carto100000colombia2019/MapServer/WMSServer' (capa 34 para vías, 0 para base) o 'https://mapas2.igac.gov.co/server/services/carto/municipios/MapServer/WMSServer'. NUNCA uses 'mapas.igac.gov.co' porque ese servidor antiguo ya no existe.
   - Para Bogotá: Ortofoto oficial IDECA 'https://serviciosgis.catastrobogota.gov.co/arcgis/services/imagenes/Ortho2017/MapServer/WMSServer' (capa 0).
   - Para Cali: IDESC 'https://ws-idesc.cali.gov.co/geoserver/wms'.
   - Para España Catastro: 'https://ovc.catastro.meh.es/Cartografia/WMS/ServidorWMS.aspx' (capa Catastro) o INSPIRE 'https://ovc.catastro.meh.es/cartografia/INSPIRE/spadgcwms.aspx'.
   - Si no estás 100% seguro de una URL fuera del catálogo, utiliza las del catálogo oficial verificado.
5. Si el usuario pregunta dudas sobre AutoCAD (ej: qué es un archivo .tfw, cómo insertar con _MAPIINSERT, resolución m/px, EPSG para su zona), explícaselo con claridad técnica.
"""
    return system_instruction


def query_openai_compatible_wms(
    prompt: str,
    api_key: str,
    base_url: str,
    models: List[str],
    provider_name: str,
    chat_history: List[Dict[str, str]],
    context_info: Optional[Dict[str, Any]] = None,
    extra_headers: Optional[Dict[str, str]] = None
) -> Dict[str, Any]:
    """
    Cliente universal compatible con la especificación OpenAI Chat Completions.
    Funciona con: OpenAI, OpenRouter, DeepSeek, Groq, Mistral, Perplexity, Ollama, vLLM, LM Studio, etc.
    """
    clean_key = api_key.strip() if api_key else ""
    is_local = "localhost" in base_url or "127.0.0.1" in base_url
    if not clean_key and not is_local:
        return {"success": False, "text": f"⚠️ Por favor, introduce tu API Key para {provider_name}."}

    system_instruction = _build_wms_system_instruction(context_info)
    messages = [{"role": "system", "content": system_instruction}]

    for msg in chat_history[-6:]:
        r = "assistant" if msg.get("role") == "model" else "user"
        messages.append({"role": r, "content": msg.get("content", "")})
    messages.append({"role": "user", "content": prompt})

    clean_base = base_url.rstrip("/")
    if not clean_base.endswith("/chat/completions"):
        endpoint = f"{clean_base}/chat/completions"
    else:
        endpoint = clean_base

    headers = {"Content-Type": "application/json"}
    if clean_key:
        headers["Authorization"] = f"Bearer {clean_key}"
    if extra_headers:
        headers.update(extra_headers)

    last_error = ""
    is_single_choice = len(models) == 1

    for model_name in models:
        payload = {
            "model": model_name,
            "messages": messages,
            "temperature": 0.4,
            "max_tokens": 1000
        }
        try:
            resp = requests.post(endpoint, headers=headers, json=payload, timeout=22)
            if resp.status_code == 200:
                data = resp.json()
                text_out = data["choices"][0]["message"]["content"]
                st.session_state["wms_active_ai_provider"] = provider_name
                st.session_state["wms_active_ai_model"] = model_name
                return {"success": True, "text": text_out, "model": model_name, "provider": provider_name}
            elif resp.status_code == 401:
                return {
                    "success": False,
                    "text": f"❌ La clave de API para {provider_name} no es válida o ha caducado. Cópiala directamente desde la consola oficial del proveedor."
                }
            elif resp.status_code == 429:
                err_data = {}
                try:
                    err_data = resp.json().get("error", {})
                except Exception:
                    pass
                err_msg = err_data.get("message", "")
                err_code = err_data.get("code", "")
                err_type = err_data.get("type", "")

                if err_code == "insufficient_quota" or err_type == "insufficient_quota" or "quota" in err_msg.lower() or "billing" in err_msg.lower():
                    return {
                        "success": False,
                        "text": (
                            f"❌ **Saldo de API agotado en tu cuenta de {provider_name}:**\n\n"
                            f"> *{err_msg or 'You exceeded your current quota, please check your plan and billing details.'}*\n\n"
                            f"💡 **Solución:** Recarga saldo en tu consola de {provider_name}, o prueba con **Google Gemini** (gratis en aistudio.google.com), **Groq** o el **Modo Local Verificado**."
                        )
                    }
                last_error = f"Límite de tasa en {provider_name}: {err_msg or '429 Too Many Requests'}"
                if is_single_choice:
                    break
                continue
            elif resp.status_code == 404:
                err_msg = ""
                try:
                    err_msg = resp.json().get("error", {}).get("message", "")
                except Exception:
                    pass
                last_error = f"El modelo '{model_name}' no existe o tu clave no tiene acceso a él en {provider_name} ({err_msg or '404 Not Found'})."
                if is_single_choice:
                    break
                continue
            else:
                try:
                    err_msg = resp.json().get("error", {}).get("message", resp.text)
                except Exception:
                    err_msg = resp.text
                last_error = f"HTTP {resp.status_code}: {err_msg}"
                if is_single_choice:
                    break
        except requests.exceptions.Timeout:
            last_error = f"Tiempo de espera agotado al consultar a {provider_name} ({model_name})."
            if is_single_choice:
                break
            continue
        except Exception as ex:
            last_error = str(ex)
            break

    return {
        "success": False,
        "text": (
            f"⚠️ No se pudo obtener respuesta de {provider_name} ({last_error}).\n\n"
            f"💡 **Recomendación:** Haz clic en **🔄 Actualizar modelos en vivo** o selecciona otro modelo del menú."
        )
    }


def query_anthropic_wms(
    prompt: str,
    api_key: str,
    chat_history: List[Dict[str, str]],
    context_info: Optional[Dict[str, Any]] = None,
    custom_model: Optional[str] = None
) -> Dict[str, Any]:
    """Envía la consulta del usuario a la API oficial de Anthropic Claude (Messages API)."""
    clean_key = api_key.strip() if api_key else ""
    if not clean_key:
        return {"success": False, "text": "⚠️ Por favor, introduce tu API Key de Anthropic (sk-ant-...)."}

    system_instruction = _build_wms_system_instruction(context_info)
    messages = []
    for msg in chat_history[-6:]:
        r = "assistant" if msg.get("role") == "model" else "user"
        messages.append({"role": r, "content": msg.get("content", "")})
    messages.append({"role": "user", "content": prompt})

    models_to_try = [custom_model.strip()] if (custom_model and custom_model.strip()) else PROVIDER_MODELS_CATALOG["anthropic"]
    endpoint = "https://api.anthropic.com/v1/messages"
    headers = {
        "x-api-key": clean_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json"
    }

    last_error = ""
    is_single_choice = len(models_to_try) == 1

    for model_name in models_to_try:
        payload = {
            "model": model_name,
            "max_tokens": 1000,
            "system": system_instruction,
            "messages": messages,
            "temperature": 0.4
        }
        try:
            resp = requests.post(endpoint, headers=headers, json=payload, timeout=22)
            if resp.status_code == 200:
                data = resp.json()
                text_out = data["content"][0]["text"]
                st.session_state["wms_active_ai_provider"] = "Anthropic Claude"
                st.session_state["wms_active_ai_model"] = model_name
                return {"success": True, "text": text_out, "model": model_name, "provider": "Anthropic Claude"}
            elif resp.status_code == 401:
                return {
                    "success": False,
                    "text": "❌ La clave de API de Anthropic (sk-ant-...) no es válida o ha caducado. Cópiala directamente desde https://console.anthropic.com/settings/keys"
                }
            elif resp.status_code == 429:
                last_error = f"Límite de tasa en Anthropic ({model_name})."
                if is_single_choice:
                    break
                continue
            else:
                try:
                    err_msg = resp.json().get("error", {}).get("message", resp.text)
                except Exception:
                    err_msg = resp.text
                last_error = f"HTTP {resp.status_code}: {err_msg}"
                if is_single_choice:
                    break
        except requests.exceptions.Timeout:
            last_error = "Tiempo de espera agotado al consultar a Anthropic."
            if is_single_choice:
                break
            continue
        except Exception as ex:
            last_error = str(ex)
            break

    return {
        "success": False,
        "text": f"⚠️ No se pudo obtener respuesta de Anthropic Claude ({last_error})."
    }


def query_gemini_wms(
    prompt: str,
    api_key: str,
    chat_history: List[Dict[str, str]],
    context_info: Optional[Dict[str, Any]] = None,
    custom_model: Optional[str] = None
) -> Dict[str, Any]:
    """Envía la consulta a la API oficial de Google Gemini (Google AI Studio vía endpoint estándar v1beta)."""
    clean_key = api_key.strip() if api_key else ""
    if not clean_key:
        return {"success": False, "text": "⚠️ Por favor, introduce tu Gemini API Key en el campo superior."}

    system_instruction = _build_wms_system_instruction(context_info)
    contents = []
    for msg in chat_history[-6:]:
        role = "user" if msg.get("role") == "user" else "model"
        contents.append({"role": role, "parts": [{"text": msg.get("content", "")}]})
    contents.append({"role": "user", "parts": [{"text": prompt}]})

    if custom_model and custom_model.strip():
        cm = custom_model.strip()
        if any(old in cm.lower() for old in ["2.5", "2.0", "1.5", "1.0"]):
            models_to_try = [cm, "gemini-3.8-flash"]
            is_single_choice = False
        else:
            models_to_try = [cm]
            is_single_choice = True
        key_error = None
    else:
        models_to_try, key_error = discover_available_gemini_models(clean_key)
        if key_error and not models_to_try:
            return {"success": False, "text": key_error}
        is_single_choice = len(models_to_try) == 1

    last_error = ""

    for model_name in models_to_try:
        endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={clean_key}"
        payload = {
            "contents": contents,
            "systemInstruction": {"parts": [{"text": system_instruction}]},
            "generationConfig": {"temperature": 0.4, "maxOutputTokens": 1000}
        }
        try:
            resp = requests.post(endpoint, headers={"Content-Type": "application/json"}, json=payload, timeout=18)
            if resp.status_code == 400 and "systemInstruction" in resp.text:
                fallback_contents = [
                    {"role": "user", "parts": [{"text": f"INSTRUCCIÓN DEL SISTEMA:\n{system_instruction}\n\nCONSULTA:\n{prompt}"}]}
                ]
                resp = requests.post(endpoint, headers={"Content-Type": "application/json"}, json={"contents": fallback_contents, "generationConfig": {"temperature": 0.4, "maxOutputTokens": 1000}}, timeout=18)

            if resp.status_code == 200:
                data = resp.json()
                candidate = data.get("candidates", [{}])[0]
                text_out = candidate.get("content", {}).get("parts", [{}])[0].get("text", "")
                if text_out:
                    st.session_state["wms_active_gemini_model"] = model_name
                    st.session_state["wms_active_ai_provider"] = "Google Gemini"
                    st.session_state["wms_chosen_model_gemini"] = model_name
                    st.session_state["sb_wms_model_choice_gemini"] = model_name
                    st.session_state["wms_active_selected_model"] = model_name
                    return {"success": True, "text": text_out, "model": model_name, "provider": "Google Gemini"}
            elif resp.status_code == 400:
                err_json = resp.json().get("error", {})
                last_error = err_json.get("message", "Petición no válida.")
                if "API key not valid" in last_error:
                    return {"success": False, "text": "❌ La clave de API de Gemini introducida no es válida. Genera una en https://aistudio.google.com/app/apikey"}
                if is_single_choice:
                    break
            elif resp.status_code == 403:
                return {"success": False, "text": "❌ Clave de API de Gemini sin permisos. Verifica que la API 'Generative Language' esté habilitada en Google AI Studio."}
            elif resp.status_code == 429:
                last_error = "Límite de cuota alcanzado temporalmente en Gemini."
                if is_single_choice:
                    break
            elif resp.status_code == 404:
                err_json = {}
                try:
                    err_json = resp.json().get("error", {})
                except Exception:
                    pass
                err_msg = err_json.get("message", "")

                # Auto-recuperación si Google AI Studio responde que el modelo está descontinuado
                suggested_m = None
                sug_match = re.search(r"use models/([a-zA-Z0-9\.\-_]+)", err_msg)
                if sug_match:
                    suggested_m = sug_match.group(1).strip()
                elif model_name != "gemini-3.8-flash":
                    suggested_m = "gemini-3.8-flash"

                if suggested_m and suggested_m != model_name:
                    retry_ep = f"https://generativelanguage.googleapis.com/v1beta/models/{suggested_m}:generateContent?key={clean_key}"
                    try:
                        r_retry = requests.post(retry_ep, headers={"Content-Type": "application/json"}, json=payload, timeout=18)
                        if r_retry.status_code == 200:
                            cand = r_retry.json().get("candidates", [{}])[0]
                            t_out = cand.get("content", {}).get("parts", [{}])[0].get("text", "")
                            if t_out:
                                st.session_state["wms_active_gemini_model"] = suggested_m
                                st.session_state["wms_active_ai_provider"] = "Google Gemini"
                                st.session_state["wms_chosen_model_gemini"] = suggested_m
                                st.session_state["sb_wms_model_choice_gemini"] = suggested_m
                                st.session_state["wms_active_selected_model"] = suggested_m
                                return {"success": True, "text": t_out, "model": suggested_m, "provider": "Google Gemini"}
                    except Exception:
                        pass

                last_error = f"El modelo '{model_name}' no existe o no está habilitado para esta clave en Google AI Studio ({err_msg or '404 Not Found'})."
                if is_single_choice:
                    break
                continue
            else:
                last_error = f"Código HTTP {resp.status_code}: {resp.text}"
                if is_single_choice:
                    break
        except requests.exceptions.Timeout:
            last_error = "Tiempo de espera agotado al consultar a Gemini."
            if is_single_choice:
                break
            continue
        except Exception as ex:
            last_error = str(ex)
            break

    return {
        "success": False,
        "text": (
            f"⚠️ No se pudo obtener respuesta de Gemini ({last_error}).\n\n"
            f"💡 **Recomendación:** Haz clic en **🔄 Actualizar modelos en vivo** o selecciona otro modelo del menú desplegable."
        )
    }


def query_universal_ai_wms(
    prompt: str,
    api_key: str,
    chat_history: List[Dict[str, str]],
    context_info: Optional[Dict[str, Any]] = None,
    provider_override: str = "auto",
    custom_url: Optional[str] = None,
    custom_model: Optional[str] = None
) -> Dict[str, Any]:
    """
    Enrutador central universal de IA. Soporta cualquier proveedor del mundo y respeta el modelo elegido por el usuario.
    """
    prov = detect_ai_provider(api_key, user_selected=provider_override)
    clean_model = custom_model.strip() if (custom_model and custom_model.strip()) else None

    if prov == "anthropic":
        return query_anthropic_wms(prompt, api_key, chat_history, context_info, clean_model)
    elif prov == "gemini":
        return query_gemini_wms(prompt, api_key, chat_history, context_info, clean_model)
    elif prov == "openrouter":
        models = [clean_model] if clean_model else PROVIDER_MODELS_CATALOG["openrouter"]
        return query_openai_compatible_wms(
            prompt, api_key, "https://openrouter.ai/api/v1", models, "OpenRouter",
            chat_history, context_info,
            extra_headers={"HTTP-Referer": "https://github.com/Miskazuela/pnoa-autocad", "X-Title": "AutoCAD PNOA OrthoExtractor"}
        )
    elif prov == "deepseek":
        models = [clean_model] if clean_model else PROVIDER_MODELS_CATALOG["deepseek"]
        return query_openai_compatible_wms(prompt, api_key, "https://api.deepseek.com", models, "DeepSeek", chat_history, context_info)
    elif prov == "groq":
        models = [clean_model] if clean_model else PROVIDER_MODELS_CATALOG["groq"]
        return query_openai_compatible_wms(prompt, api_key, "https://api.groq.com/openai/v1", models, "Groq", chat_history, context_info)
    elif prov == "mistral":
        models = [clean_model] if clean_model else PROVIDER_MODELS_CATALOG["mistral"]
        return query_openai_compatible_wms(prompt, api_key, "https://api.mistral.ai/v1", models, "Mistral AI", chat_history, context_info)
    elif prov == "perplexity":
        models = [clean_model] if clean_model else PROVIDER_MODELS_CATALOG["perplexity"]
        return query_openai_compatible_wms(prompt, api_key, "https://api.perplexity.ai", models, "Perplexity AI", chat_history, context_info)
    elif prov == "custom":
        url = custom_url.strip() if custom_url and custom_url.strip() else "http://localhost:11434/v1"
        models = [clean_model] if clean_model else PROVIDER_MODELS_CATALOG["custom"]
        return query_openai_compatible_wms(prompt, api_key, url, models, "Servidor Personalizado / Local", chat_history, context_info)
    else:  # openai
        models = [clean_model] if clean_model else PROVIDER_MODELS_CATALOG["openai"]
        return query_openai_compatible_wms(prompt, api_key, "https://api.openai.com/v1", models, "OpenAI", chat_history, context_info)


# Alias para compatibilidad total con código existente
query_ai_wms = query_universal_ai_wms
query_openai_wms = lambda p, k, h, c=None: query_universal_ai_wms(p, k, h, c, provider_override="openai")


# --------------------------------------------------------------------------------------
# 5. PARSEO DE ACCIONES WMS Y COMPONENTE MODAL / FLOTANTE
# --------------------------------------------------------------------------------------
def _parse_and_render_wms_actions(text: str):
    """Detecta bloques [APPLY_WMS: {...}] y renderiza un botón de aplicación directa."""
    pattern = r"\[APPLY_WMS:\s*(\{.*?\})\s*\]"
    clean_text = re.sub(pattern, "", text).strip()
    st.markdown(clean_text)

    matches = re.findall(pattern, text)
    for m in matches:
        try:
            data = json.loads(m)
            w_name = data.get("name", "Servicio WMS")
            w_url = data.get("url", "")
            w_layer = data.get("layer", "")
            btn_key = f"apply_wms_ai_{abs(hash(w_url + w_layer))}"
            if st.button(f"🚀 Cargar en la aplicación: {w_name}", key=btn_key, type="primary"):
                apply_wms_to_application(w_url, w_layer, w_name)
        except Exception:
            pass


def apply_wms_to_application(url: str, layer: str, name: str):
    """Configura el servicio WMS en la sesión activa de Streamlit y fuerza la recarga."""
    st.session_state["wms_dialog_is_open"] = False
    st.session_state["pending_sidebar_service"] = "⚙️ Agregar WMS externo (Cualquier servidor WMS del mundo)"
    st.session_state["pending_custom_wms_url"] = url
    st.session_state["pending_custom_wms_layer"] = layer
    st.toast(f"✅ ¡Servicio '{name}' configurado en la app!", icon="🌍")
    st.rerun()


def render_wms_assistant_content(
    active_epsg: Optional[Any] = None,
    current_service_name: Optional[str] = None,
    uploaded_filename: Optional[str] = None,
    detected_zone: Optional[Dict[str, Any]] = None
):
    """
    Renderiza el contenido interno del Asistente WMS (utilizable dentro del modal st.dialog o embebido).
    """
    if "wms_bot_api_key" not in st.session_state:
        st.session_state["wms_bot_api_key"] = os.environ.get("OPENAI_API_KEY") or os.environ.get("GEMINI_API_KEY", "")
    if "wms_chat_history" not in st.session_state:
        st.session_state["wms_chat_history"] = [
            {
                "role": "model",
                "content": (
                    "👋 **¡Hola! Soy tu Asistente Cartográfico y de Servicios WMS (Mundial y España).**\n\n"
                    "Puedo ayudarte a encontrar cualquier capa oficial para tus proyectos en AutoCAD o Civil 3D:\n"
                    "- 🏛️ **Catastro y Parcelas** (España DGC, Navarra, País Vasco, INSPIRE)\n"
                    "- 🌊 **Aguas y Zonas Inundables** (SNCZI MITECO, DPH, Cuencas)\n"
                    "- 🗺️ **Topografía y Relieve** (Curvas de nivel MTN25, Sombreado LiDAR, Pendientes)\n"
                    "- 🌲 **Medio Ambiente** (Red Natura 2000, Montes MUP, Espacios Protegidos ENP)\n"
                    "- 🌎 **América y Global** (Colombia IGAC/SGC, México INEGI, Chile, Argentina, EE.UU. USGS, Copernicus, OpenStreetMap)\n\n"
                    "Escríbeme lo que necesitas o selecciona uno de los accesos rápidos a continuación."
                )
            }
        ]

    # Barra informativa de contexto actual (lo que el usuario está viendo en su plano)
    epsg_disp = str(active_epsg or st.session_state.get("wms_active_epsg", "25830"))
    file_disp = uploaded_filename or st.session_state.get("wms_uploaded_filename", "Ninguno (Dibujando en visor)")
    serv_disp = current_service_name or st.session_state.get("wms_current_service_name", "Ortofoto PNOA (IGN)")
    zone_info = detected_zone or st.session_state.get("wms_detected_zone") or st.session_state.get("detected_zone_country")
    zone_disp = f"{zone_info.get('flag', '📍')} {zone_info.get('name', '')}" if (zone_info and isinstance(zone_info, dict)) else None

    # Deducir ámbito geográfico del proyecto para resolver preguntas como 'capa de hidrologia del archivo cargado'
    project_geo_keys = infer_project_geo_keys(
        active_epsg=epsg_disp,
        detected_zone=zone_info,
        uploaded_filename=file_disp
    )

    zone_badge = f'<div>🌍 <span style="color: #f59e0b; font-weight: 600;">{zone_disp}</span></div>' if zone_disp else ''
    st.markdown(f"""
    <div style="background: rgba(15, 23, 42, 0.8); border: 1px solid rgba(56, 189, 248, 0.25); border-radius: 8px; padding: 5px 8px; margin-bottom: 8px; display: flex; flex-wrap: wrap; gap: 8px; align-items: center; font-size: 11px; color: #cbd5e1;">
        <div>📍 <code style="color: #38bdf8; font-weight: 600;">EPSG:{epsg_disp}</code></div>
        <div>📁 <span style="color: #94a3b8;">{file_disp[:20]}</span></div>
        {zone_badge}
        <div>🛰️ <span style="color: #34d399; font-weight: 500;">{serv_disp[:24]}</span></div>
    </div>
    """, unsafe_allow_html=True)

    user_key = st.session_state.get("wms_bot_api_key", "").strip()
    has_key = bool(user_key)
    cur_p_setting = st.session_state.get("wms_selected_ai_provider", "auto")
    effective_prov = detect_ai_provider(user_key, user_selected=cur_p_setting)
    disp_m = st.session_state.get("wms_active_selected_model", "gemini-3.8-flash")

    # Pestañas compactas del Asistente en ventana flotante
    tab_chat, tab_catalog, tab_inspect, tab_config = st.tabs([
        "💬 Chat",
        "📚 Directorio",
        "🔍 Inspeccionar",
        "⚙️ Ajustes"
    ])

    # ------------------------------------------------------------------------------
    # PESTAÑA 1: CHAT CON EL ASISTENTE
    # ------------------------------------------------------------------------------
    with tab_chat:
        col_st_lbl, col_st_clear = st.columns([5, 1])
        with col_st_lbl:
            if has_key or cur_p_setting == "custom":
                eff_name = effective_prov.capitalize()
                st.markdown(f"<div style='font-size: 11.5px; color: #34d399; font-weight: 600;'>✨ Modo IA: <span style='color: #f8fafc;'>{eff_name} ({disp_m})</span></div>", unsafe_allow_html=True)
            else:
                st.markdown("<div style='font-size: 11.5px; color: #38bdf8; font-weight: 600;'>🟢 Modo Catálogo Local (Offline y Gratis)</div>", unsafe_allow_html=True)
        with col_st_clear:
            if st.button("🗑️", key="btn_clear_chat_modal", help="Reiniciar conversación"):
                st.session_state["wms_chat_history"] = []
                st.rerun(scope="fragment")

        col_q1, col_q2 = st.columns(2)
        selected_prompt = None
        with col_q1:
            if st.button("🏛️ Catastro / Parcelas", key="chip_modal_btn_0", use_container_width=True):
                selected_prompt = "Necesito la cartografía del Catastro para ver parcelas y linderos"
            if st.button("⛰️ Curvas de Nivel MTN", key="chip_modal_btn_2", use_container_width=True):
                selected_prompt = "Necesito curvas de nivel y mapa topográfico ráster MTN"
        with col_q2:
            if st.button("🌊 Zonas Inundables", key="chip_modal_btn_1", use_container_width=True):
                selected_prompt = "Busco las zonas inundables de periodo de retorno 100 y 500 años de MITECO"
            if st.button("🌐 Calles / OpenStreetMap", key="chip_modal_btn_4", use_container_width=True):
                selected_prompt = "Necesito una capa base mundial de calles y carreteras con OpenStreetMap"

        chat_box = st.container(height=310)
        bot_avatar_img = get_bot_avatar_path()
        with chat_box:
            for msg in st.session_state["wms_chat_history"]:
                role = msg["role"]
                av = bot_avatar_img if role == "model" else None
                with st.chat_message(role, avatar=av):
                    if role == "model":
                        _parse_and_render_wms_actions(msg["content"])
                    else:
                        st.markdown(msg["content"])

            new_turn_container = st.container()

        user_input = st.chat_input("Escribe tu pregunta sobre capas WMS o tu plano...")

        query_to_run = selected_prompt or user_input
        if query_to_run:
            with new_turn_container:
                with st.chat_message("user"):
                    st.markdown(query_to_run)
                st.session_state["wms_chat_history"].append({"role": "user", "content": query_to_run})

                with st.chat_message("model", avatar=bot_avatar_img):
                    current_key = st.session_state.get("wms_bot_api_key", "").strip()
                    active_p_setting = st.session_state.get("wms_selected_ai_provider", "auto")
                    if current_key or active_p_setting == "custom":
                        eff_prov = detect_ai_provider(current_key, user_selected=active_p_setting)
                        prov_name = eff_prov.capitalize()
                        with st.spinner(f"Consultando a {prov_name}..."):
                            context_dict = {
                                "active_epsg": epsg_disp,
                                "current_service": serv_disp,
                                "uploaded_filename": file_disp,
                                "detected_zone": zone_disp or "No especificado"
                            }
                            res = query_universal_ai_wms(
                                prompt=query_to_run,
                                api_key=current_key,
                                chat_history=st.session_state["wms_chat_history"][:-1],
                                context_info=context_dict,
                                provider_override=active_p_setting,
                                custom_url=st.session_state.get("wms_custom_ai_url"),
                                custom_model=st.session_state.get("wms_active_selected_model") or st.session_state.get("wms_custom_ai_model")
                            )
                            bot_response = res["text"]

                            # Si hubo algún problema con la API de IA, anexamos automáticamente
                            # las recomendaciones del catálogo local para no dejar la consulta sin respuesta.
                            if not res.get("success", False):
                                local_matches = search_wms_catalog(query_to_run, project_geo_fallback=project_geo_keys)
                                if local_matches:
                                    top = local_matches[:3]
                                    lines = [
                                        bot_response,
                                        "\n\n---\n🔍 **Recomendaciones automáticas del Catálogo Oficial Local:**\n"
                                    ]
                                    for m in top:
                                        lines.append(f"### {m['name']}")
                                        lines.append(f"- **Ámbito:** {m['region']} | **Categoría:** {m['category']}")
                                        lines.append(f"- **Descripción:** {m['description']}")
                                        lines.append(f"- **URL Base:** `{m['url']}`")
                                        lines.append(f"- **Capa recomendada:** `{m['default_layer']}`")
                                        lines.append(f"[APPLY_WMS: {json.dumps({'name': m['name'], 'url': m['url'], 'layer': m['default_layer']})}]\n")
                                    bot_response = "\n".join(lines)

                            _parse_and_render_wms_actions(bot_response)
                    else:
                        matches = search_wms_catalog(query_to_run, project_geo_fallback=project_geo_keys)
                        clean_run_q = _normalize_text(query_to_run)
                        is_context_q = bool(set(clean_run_q.split()).intersection(CONTEXT_PROJECT_TRIGGERS))

                        if matches:
                            top = matches[:3]
                            if is_context_q and zone_disp:
                                header_lbl = f"🔍 **Encontré {len(matches)} servicios oficiales para la ubicación de tu plano ({zone_disp}):**\n"
                            else:
                                header_lbl = f"🔍 **Encontré {len(matches)} servicios oficiales para tu consulta:**\n"
                            lines = [header_lbl]
                            for m in top:
                                lines.append(f"### {m['name']}")
                                lines.append(f"- **Ámbito:** {m['region']} | **Categoría:** {m['category']}")
                                lines.append(f"- **Descripción:** {m['description']}")
                                lines.append(f"- **URL Base:** `{m['url']}`")
                                lines.append(f"- **Capa recomendada:** `{m['default_layer']}`")
                                lines.append(f"[APPLY_WMS: {json.dumps({'name': m['name'], 'url': m['url'], 'layer': m['default_layer']})}]\n")
                            if len(matches) > 3:
                                lines.append(f"*Y {len(matches) - 3} servicios adicionales disponibles en la pestaña '📚 Directorio Mundial'.*")
                            bot_response = "\n".join(lines)
                        else:
                            detected_geos = _detect_query_geo(query_to_run)
                            bot_response = build_smart_offline_response(
                                query=query_to_run,
                                detected_geos=detected_geos,
                                zone_disp=zone_disp,
                                is_context_q=is_context_q
                            )
                        _parse_and_render_wms_actions(bot_response)

                st.session_state["wms_chat_history"].append({"role": "model", "content": bot_response})

    # ------------------------------------------------------------------------------
    # PESTAÑA 2: DIRECTORIO MUNDIAL DE SERVICIOS
    # ------------------------------------------------------------------------------
    with tab_catalog:
        col_f1, col_f2 = st.columns(2)
        categories = ["Todas las categorías"] + sorted(list({item["category"] for item in WMS_DATABASE}))
        with col_f1:
            sel_cat = st.selectbox("Categoría:", options=categories, key="dir_modal_cat_filter")
        with col_f2:
            regions = [
                "Todas las regiones", "Global", "España", "América", "Colombia", "Bogotá", "Medellín", "Cali", "México", "Chile", "Argentina", "Perú",
                "Estados Unidos", "Canadá", "Europa", "Francia", "Alemania", "Portugal", "Australia"
            ]
            sel_reg = st.selectbox("Región / País:", options=regions, key="dir_modal_reg_filter")
        search_txt = st.text_input("Buscar por palabra clave:", placeholder="Ej: parcelas, lidar, rio, usgs...", key="dir_modal_search_txt")

        dir_results = search_wms_catalog(search_txt, category_filter=sel_cat, region_filter=sel_reg)
        st.caption(f"Mostrando **{len(dir_results)}** servicios cartográficos oficiales verificados:")

        for srv in dir_results:
            with st.container():
                c_info, c_action = st.columns([3.5, 1.2])
                with c_info:
                    st.markdown(f"**{srv['name']}** — <span style='color: #38bdf8; font-size: 11px;'>{srv['category']} ({srv['region']})</span>", unsafe_allow_html=True)
                    st.caption(srv["description"])
                    st.code(f"URL: {srv['url']}\nCapa: {srv['default_layer']}", language="text")
                with c_action:
                    btn_id = f"dir_modal_apply_{srv['id']}"
                    if st.button("🚀 Cargar", key=btn_id, use_container_width=True, type="primary"):
                        apply_wms_to_application(srv["url"], srv["default_layer"], srv["name"])
                st.divider()

    # ------------------------------------------------------------------------------
    # PESTAÑA 3: INSPECTOR DE URL EXTERNA (GETCAPABILITIES EN VIVO)
    # ------------------------------------------------------------------------------
    with tab_inspect:
        st.markdown("<p style='font-size: 12px; color: #cbd5e1;'>Pega la URL de cualquier servidor WMS externo para inspeccionar capas y EPSG soportados:</p>", unsafe_allow_html=True)
        inspect_url = st.text_input(
            "URL del servidor WMS a inspeccionar:",
            placeholder="https://servidor-geoportal.com/.../wms",
            key="inspector_modal_wms_input"
        )
        if st.button("🔍 Inspeccionar Servidor en Vivo", key="btn_modal_run_inspector", type="primary", use_container_width=True):
            if inspect_url:
                with st.spinner("Consultando GetCapabilities al servidor..."):
                    report = inspect_wms_live(inspect_url)
                    if report["success"]:
                        st.success(f"✅ Conexión exitosa con: **{report['title']}**")
                        if report["abstract"]:
                            st.info(report["abstract"])

                        st.write(f"📋 **Capas publicadas detectadas ({len(report['layers'])}):**")
                        for lyr in report["layers"][:25]:
                            col_l_name, col_l_btn = st.columns([3.5, 1.2])
                            with col_l_name:
                                st.markdown(f"• **`{lyr['name']}`** : {lyr['title']}")
                            with col_l_btn:
                                if st.button("Usar", key=f"use_modal_insp_lyr_{abs(hash(lyr['name']))}", use_container_width=True):
                                    apply_wms_to_application(report["url"], lyr["name"], f"{report['title']} - {lyr['name']}")

                        if len(report["layers"]) > 25:
                            st.caption(f"*(Mostrando las primeras 25 de {len(report['layers'])} capas)*")

                        if report["supported_crs"]:
                            with st.expander("🌐 Ver sistemas de coordenadas (CRS / EPSG) soportados"):
                                st.write(", ".join(report["supported_crs"]))
                    else:
                        st.error(f"❌ Error al inspeccionar el servicio: {report['error']}")
            else:
                st.warning("Por favor, introduce una URL para inspeccionar.")

    # ------------------------------------------------------------------------------
    # PESTAÑA 4: AJUSTES Y CONFIGURACIÓN DE IA
    # ------------------------------------------------------------------------------
    with tab_config:
        st.markdown("<p style='font-size: 13px; font-weight: 700; color: #f8fafc; margin-bottom: 2px;'>⚙️ Configuración del Motor de IA</p>", unsafe_allow_html=True)
        user_key_in = st.text_input(
            "🔑 API Key de tu servicio de IA:",
            value=st.session_state.get("wms_bot_api_key", ""),
            type="password",
            placeholder="AIzaSy... (Gemini), sk-... (OpenAI), gsk_... (Groq)",
            help="Soporta cualquier servicio de IA del mundo. Si la dejas vacía, el bot opera en Modo Local Verificado 100% gratis y offline."
        )
        st.session_state["wms_bot_api_key"] = user_key_in.strip()

        c_prov, c_model = st.columns([1, 1.4])
        with c_prov:
            provider_options = [
                ("auto", f"🔍 Auto ({effective_prov.capitalize() if effective_prov != 'none' else 'Por clave'})"),
                ("gemini", "Google Gemini"),
                ("openai", "OpenAI (ChatGPT)"),
                ("anthropic", "Anthropic Claude"),
                ("groq", "Groq (Ultra-rápido)"),
                ("deepseek", "DeepSeek"),
                ("openrouter", "OpenRouter"),
                ("mistral", "Mistral AI"),
                ("perplexity", "Perplexity AI"),
                ("custom", "⚙️ Servidor Local (Ollama)")
            ]
            prov_keys = [p[0] for p in provider_options]
            prov_labels = [p[1] for p in provider_options]
            cur_p_idx = prov_keys.index(cur_p_setting) if cur_p_setting in prov_keys else 0
            sel_label = st.selectbox("Proveedor:", options=prov_labels, index=cur_p_idx, key="sb_wms_prov_selector")
            chosen_prov = prov_keys[prov_labels.index(sel_label)]
            st.session_state["wms_selected_ai_provider"] = chosen_prov
            if chosen_prov != "auto":
                effective_prov = chosen_prov

        with c_model:
            cust_url_active = st.session_state.get("wms_custom_ai_url", "http://localhost:11434/v1")
            base_models = discover_provider_models(
                provider=effective_prov,
                api_key=user_key_in.strip(),
                custom_url=cust_url_active,
                force_refresh=False
            )
            model_choices = list(base_models) + ["✏️ Personalizado..."]

            prov_state_key = f"wms_chosen_model_{effective_prov}"
            prev_m = st.session_state.get(prov_state_key, base_models[0])

            sb_model_key = f"sb_wms_model_choice_{effective_prov}"
            if effective_prov == "gemini":
                cur_sb = st.session_state.get(sb_model_key)
                if cur_sb and (cur_sb not in model_choices or any(old in str(cur_sb).lower() for old in ["2.5", "2.0", "1.5", "1.0"])):
                    st.session_state.pop(sb_model_key, None)
                if prev_m and any(old in str(prev_m).lower() for old in ["2.5", "2.0", "1.5", "1.0"]):
                    prev_m = base_models[0]
                    st.session_state[prov_state_key] = prev_m

            if prev_m in base_models:
                m_idx = base_models.index(prev_m)
            elif prev_m == "custom_input":
                m_idx = len(model_choices) - 1
            else:
                m_idx = 0

            sel_m_choice = st.selectbox(
                "Modelo:",
                options=model_choices,
                index=m_idx,
                key=f"sb_wms_model_choice_{effective_prov}"
            )

            if sel_m_choice == "✏️ Personalizado...":
                st.session_state[prov_state_key] = "custom_input"
                custom_m_in = st.text_input(
                    "Nombre exacto:",
                    value=st.session_state.get(f"wms_custom_name_{effective_prov}", ""),
                    placeholder="Ej: gemini-3.8-flash, gpt-4o"
                )
                active_model_name = custom_m_in.strip() if custom_m_in.strip() else base_models[0]
                st.session_state[f"wms_custom_name_{effective_prov}"] = active_model_name
            else:
                active_model_name = sel_m_choice
                st.session_state[prov_state_key] = active_model_name

            st.session_state["wms_active_selected_model"] = active_model_name

        if st.button("🔄 Actualizar lista de modelos en vivo", key=f"btn_ref_m_{effective_prov}", use_container_width=True):
            for k in list(st.session_state.keys()):
                if k.startswith("_cached_"):
                    st.session_state.pop(k, None)
            st.rerun()

        if effective_prov == "custom":
            cust_url_in = st.text_input(
                "URL Base Servidor Local:",
                value=st.session_state.get("wms_custom_ai_url", "http://localhost:11434/v1"),
                placeholder="http://localhost:11434/v1"
            )
            st.session_state["wms_custom_ai_url"] = cust_url_in.strip()
        else:
            with st.expander("🔌 Conectar Servidor Local (Ollama / LM Studio)", expanded=False):
                if st.button("Activar Ollama (localhost:11434)", key="btn_activate_local_ollama", use_container_width=True):
                    st.session_state["wms_selected_ai_provider"] = "custom"
                    st.rerun()


# --------------------------------------------------------------------------------------
# 6. DIÁLOGO MODAL NATIVO (@st.dialog) Y BOTÓN FLOTANTE EN ESQUINA INFERIOR DERECHA
# --------------------------------------------------------------------------------------
def _on_wms_dialog_dismiss():
    st.session_state["wms_dialog_is_open"] = False


if hasattr(st, "dialog"):
    try:
        @st.dialog("🤖 GeoBot WMS", on_dismiss=_on_wms_dialog_dismiss)
        def _wms_assistant_dialog_view(active_epsg=None, current_service_name=None, uploaded_filename=None):
            render_wms_assistant_content(
                active_epsg=active_epsg,
                current_service_name=current_service_name,
                uploaded_filename=uploaded_filename
            )
    except TypeError:
        @st.dialog("🤖 GeoBot WMS")
        def _wms_assistant_dialog_view(active_epsg=None, current_service_name=None, uploaded_filename=None):
            render_wms_assistant_content(
                active_epsg=active_epsg,
                current_service_name=current_service_name,
                uploaded_filename=uploaded_filename
            )
elif hasattr(st, "experimental_dialog"):
    @st.experimental_dialog("🤖 GeoBot WMS")
    def _wms_assistant_dialog_view(active_epsg=None, current_service_name=None, uploaded_filename=None):
        render_wms_assistant_content(
            active_epsg=active_epsg,
            current_service_name=current_service_name,
            uploaded_filename=uploaded_filename
        )
else:
    def _wms_assistant_dialog_view(active_epsg=None, current_service_name=None, uploaded_filename=None):
        render_wms_assistant_content(
            active_epsg=active_epsg,
            current_service_name=current_service_name,
            uploaded_filename=uploaded_filename
        )


def show_wms_assistant_dialog(
    active_epsg: Optional[Any] = None,
    current_service_name: Optional[str] = None,
    uploaded_filename: Optional[str] = None,
    detected_zone: Optional[Dict[str, Any]] = None
):
    """Marca el diálogo como abierto y solicita ejecución."""
    if active_epsg is not None:
        st.session_state["wms_active_epsg"] = active_epsg
    if current_service_name is not None:
        st.session_state["wms_current_service_name"] = current_service_name
    if uploaded_filename is not None:
        st.session_state["wms_uploaded_filename"] = uploaded_filename
    if detected_zone is not None:
        st.session_state["wms_detected_zone"] = detected_zone
    st.session_state["wms_dialog_is_open"] = True
    st.rerun()


def render_floating_assistant_button(
    active_epsg: Optional[Any] = None,
    current_service_name: Optional[str] = None,
    uploaded_filename: Optional[str] = None,
    detected_zone: Optional[Dict[str, Any]] = None
):
    """
    Renderiza un Botón Flotante interactivo en la esquina inferior derecha.
    Al abrirse, despliega una ventana emergente compacta estilo widget (tipo Esri Colombia / Intercom)
    que NO bloquea la pantalla y permite interactuar con el visor de mapas y planos CAD.
    """
    if "wms_dialog_is_open" not in st.session_state:
        st.session_state["wms_dialog_is_open"] = False

    if active_epsg is not None:
        st.session_state["wms_active_epsg"] = active_epsg
    if current_service_name is not None:
        st.session_state["wms_current_service_name"] = current_service_name
    if uploaded_filename is not None:
        st.session_state["wms_uploaded_filename"] = uploaded_filename
    if detected_zone is not None:
        st.session_state["wms_detected_zone"] = detected_zone

    is_open = st.session_state.get("wms_dialog_is_open", False)
    b64_avatar = get_bot_avatar_b64()
    img_css = f"background-image: url('data:image/png;base64,{b64_avatar}') !important;" if b64_avatar else ""

    if is_open:
        btn_label = "✕"
        bubble_html = ""
        btn_state_css = """
        div.st-key-btn_floating_assistant button {
            width: 58px !important;
            height: 58px !important;
            border-radius: 50% !important;
            padding: 0 !important;
            background-color: #0284c7 !important;
            background-image: none !important;
            border: 2px solid #ffffff !important;
            box-shadow: 0 8px 24px rgba(2, 132, 199, 0.6), 0 0 16px rgba(56, 189, 248, 0.4) !important;
            animation: none !important;
            color: #ffffff !important;
            font-size: 26px !important;
            font-weight: 700 !important;
            line-height: 54px !important;
            text-align: center !important;
            display: flex !important;
            align-items: center !important;
            justify-content: center !important;
        }
        div.st-key-btn_floating_assistant button:hover {
            transform: scale(1.08) rotate(90deg) !important;
            background-color: #0369a1 !important;
            box-shadow: 0 10px 28px rgba(2, 132, 199, 0.8) !important;
        }
        """
    else:
        btn_label = " "
        bubble_html = """
        <div class="bot-speech-bubble">
            <span>✨ GeoBot WMS</span>
        </div>
        """
        btn_state_css = f"""
        div.st-key-btn_floating_assistant button {{
            width: 66px !important;
            height: 66px !important;
            border-radius: 50% !important;
            padding: 0 !important;
            background-color: #0b1329 !important;
            background-repeat: no-repeat !important;
            background-position: center !important;
            background-size: 88% !important;
            {img_css}
            border: 2.5px solid #38bdf8 !important;
            animation: epicBotFloat 3.8s ease-in-out infinite, epicCosmicGlow 2.8s infinite !important;
            color: transparent !important;
            font-size: 0px !important;
        }}
        div.st-key-btn_floating_assistant button:hover {{
            transform: scale(1.15) translateY(-5px) !important;
            border-color: #67e8f9 !important;
            box-shadow: 0 0 32px rgba(56, 189, 248, 0.95), 0 14px 35px rgba(0, 0, 0, 0.75) !important;
            filter: drop-shadow(0 0 16px #38bdf8) !important;
        }}
        """

    st.markdown(f"""
    <style>
    @keyframes epicBotFloat {{
        0% {{ transform: translateY(0px) rotate(0deg); }}
        50% {{ transform: translateY(-8px) rotate(1.5deg); }}
        100% {{ transform: translateY(0px) rotate(0deg); }}
    }}

    @keyframes epicCosmicGlow {{
        0% {{
            box-shadow: 0 0 0 0 rgba(56, 189, 248, 0.75), 0 8px 20px rgba(2, 132, 199, 0.5);
        }}
        70% {{
            box-shadow: 0 0 0 16px rgba(56, 189, 248, 0), 0 10px 28px rgba(14, 165, 233, 0.75);
        }}
        100% {{
            box-shadow: 0 0 0 0 rgba(56, 189, 248, 0), 0 8px 20px rgba(2, 132, 199, 0.5);
        }}
    }}

    @keyframes bubbleFloat {{
        0% {{ transform: translateY(0px); opacity: 0.95; }}
        50% {{ transform: translateY(-4px); opacity: 1; }}
        100% {{ transform: translateY(0px); opacity: 0.95; }}
    }}

    @keyframes slideUpWidget {{
        from {{
            opacity: 0;
            transform: translateY(24px) scale(0.96);
        }}
        to {{
            opacity: 1;
            transform: translateY(0) scale(1);
        }}
    }}

    /* Botón flotante base */
    div.st-key-btn_floating_assistant button {{
        position: fixed !important;
        bottom: 24px !important;
        right: 24px !important;
        z-index: 999999 !important;
        cursor: pointer !important;
        transition: all 0.25s cubic-bezier(0.34, 1.56, 0.64, 1) !important;
    }}

    {btn_state_css}

    /* Bocadillo animado flotante sobre el botón */
    .bot-speech-bubble {{
        position: fixed;
        bottom: 100px;
        right: 24px;
        z-index: 999998;
        background: rgba(15, 23, 42, 0.92);
        backdrop-filter: blur(10px);
        border: 1px solid rgba(56, 189, 248, 0.5);
        border-radius: 16px 16px 4px 16px;
        padding: 6px 12px;
        color: #f0f9ff;
        font-size: 12px;
        font-weight: 700;
        box-shadow: 0 8px 24px rgba(0, 0, 0, 0.5), 0 0 16px rgba(56, 189, 248, 0.3);
        animation: bubbleFloat 3.8s ease-in-out infinite;
        pointer-events: none;
        display: flex;
        align-items: center;
        gap: 6px;
    }}
    .bot-speech-bubble::after {{
        content: '';
        position: absolute;
        bottom: -7px;
        right: 28px;
        width: 0;
        height: 0;
        border-left: 7px solid transparent;
        border-right: 7px solid transparent;
        border-top: 7px solid rgba(15, 23, 42, 0.92);
    }}

    /* ------------------------------------------------------------------------- */
    /* VENTANA EMERGENTE TIPO WIDGET (TIPO ESRI COLOMBIA / INTERCOM)            */
    /* ------------------------------------------------------------------------- */
    
    /* 1. Backdrop contenedor transparente posicionado abajo a la derecha */
    div[data-testid="stDialog"],
    div.stDialog {{
        position: fixed !important;
        inset: 0 !important;
        z-index: 999990 !important;
        background-color: transparent !important;
        background: transparent !important;
        backdrop-filter: none !important;
        display: flex !important;
        align-items: flex-end !important;
        justify-content: flex-end !important;
        padding: 0 24px 92px 0 !important;
        margin: 0 !important;
    }}

    /* 2. Tarjeta del widget flotante (opaco, 100% interactivo, fondo sólido #0b1329) */
    div[data-testid="stDialog"] > div,
    div.stDialog > div {{
        width: 410px !important;
        max-width: calc(100vw - 32px) !important;
        height: 600px !important;
        max-height: calc(100vh - 120px) !important;
        margin: 0 !important;
        padding: 0 !important;
        background-color: #0b1329 !important;
        background: #0b1329 !important;
        opacity: 1 !important;
        pointer-events: auto !important;
        border: 1.5px solid rgba(56, 189, 248, 0.45) !important;
        border-radius: 18px !important;
        box-shadow: 0 16px 45px rgba(0, 0, 0, 0.9), 0 0 25px rgba(56, 189, 248, 0.3) !important;
        overflow: hidden !important;
        display: flex !important;
        flex-direction: column !important;
        animation: slideUpWidget 0.28s cubic-bezier(0.16, 1, 0.3, 1) !important;
    }}

    /* Forzar fondo sólido en todos los contenedores hijos del widget para que nada transparente traspase */
    div[data-testid="stDialog"] [role="dialog"],
    div[data-testid="stDialog"] div[data-testid="stVerticalBlock"],
    div[data-testid="stDialog"] div[data-testid="stTabs"] {{
        background-color: #0b1329 !important;
        background: #0b1329 !important;
    }}

    /* 3. Cabecera azul estilo Esri Colombia */
    div[data-testid="stDialog"] h2,
    div[data-testid="stDialogHeader"] {{
        background: linear-gradient(135deg, #0284c7 0%, #1e40af 100%) !important;
        padding: 12px 16px !important;
        margin: 0 !important;
        border-top-left-radius: 16px !important;
        border-top-right-radius: 16px !important;
        border-bottom: 1px solid rgba(255, 255, 255, 0.15) !important;
        color: #ffffff !important;
        font-size: 15px !important;
        font-weight: 700 !important;
        letter-spacing: -0.2px !important;
    }}

    /* Botón de cerrar 'X' en la cabecera */
    div[data-testid="stDialog"] button[aria-label="Close"],
    div[data-testid="stDialogHeader"] button {{
        top: 10px !important;
        right: 14px !important;
        color: #ffffff !important;
        background: rgba(255, 255, 255, 0.2) !important;
        border-radius: 50% !important;
        width: 26px !important;
        height: 26px !important;
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
        transition: background 0.2s ease !important;
    }}
    div[data-testid="stDialog"] button[aria-label="Close"]:hover,
    div[data-testid="stDialogHeader"] button:hover {{
        background: rgba(255, 255, 255, 0.35) !important;
    }}

    /* Scroll interior del cuerpo del widget */
    div[data-testid="stDialog"] div[data-testid="stVerticalBlock"] {{
        overflow-y: auto !important;
        padding: 10px 14px !important;
        height: 100% !important;
    }}

    /* Estilo de pestañas compacto para el widget */
    div[data-testid="stDialog"] div[data-testid="stTabs"] [data-baseweb="tab-list"] {{
        gap: 3px !important;
        margin-bottom: 6px !important;
        background: transparent !important;
    }}

    div[data-testid="stDialog"] div[data-testid="stTabs"] [data-baseweb="tab"] {{
        padding: 4px 8px !important;
        font-size: 11.5px !important;
        font-weight: 600 !important;
    }}

    /* Burbujas de chat estilo widget */
    div[data-testid="stDialog"] div[data-testid="stChatMessage"] {{
        background-color: rgba(30, 41, 59, 0.9) !important;
        border: 1px solid rgba(56, 189, 248, 0.25) !important;
        border-radius: 12px !important;
        padding: 8px 12px !important;
        margin-bottom: 8px !important;
    }}

    /* Adaptación a dispositivos móviles */
    @media (max-width: 640px) {{
        div[data-testid="stDialog"],
        div.stDialog {{
            padding: 0 12px 80px 0 !important;
        }}
        div[data-testid="stDialog"] > div,
        div.stDialog > div {{
            width: calc(100vw - 24px) !important;
            height: calc(100vh - 96px) !important;
        }}
        div.st-key-btn_floating_assistant button {{
            right: 14px !important;
            bottom: 14px !important;
        }}
    }}
    </style>
    {bubble_html}
    """, unsafe_allow_html=True)

    if st.button(btn_label, key="btn_floating_assistant", help="Haz clic para abrir/cerrar GeoBot WMS"):
        st.session_state["wms_dialog_is_open"] = not is_open
        st.rerun()

    if st.session_state.get("wms_dialog_is_open", False):
        _wms_assistant_dialog_view(
            active_epsg=st.session_state.get("wms_active_epsg", active_epsg),
            current_service_name=st.session_state.get("wms_current_service_name", current_service_name),
            uploaded_filename=st.session_state.get("wms_uploaded_filename", uploaded_filename)
        )


# Alias para máxima retrocompatibilidad
render_wms_assistant_panel = render_wms_assistant_content
