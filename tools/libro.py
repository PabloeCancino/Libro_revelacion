#!/usr/bin/env python3
"""Utilidades editoriales comunes a todos los libros publicados con mdBook.

Uso:
    python3 tools/libro.py orden     # capítulos en el orden de src/SUMMARY.md (uno por línea)
    python3 tools/libro.py revisar   # revisión editorial; termina con código 1 si hay errores

El orden de los PDF/EPUB se toma de SUMMARY.md (el mismo índice que usa el
sitio web), no del orden alfabético de los archivos. Así el libro descargable
y el sitio nunca pueden quedar en órdenes distintos.
"""

import os
import re
import subprocess
import sys
import tomllib
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
SRC = RAIZ / "src"
ENLACE_MD = re.compile(r"\]\(\s*(?:\./)?([^)#\s]+\.md)(#[^)\s]*)?\s*\)")

# Archivos que nunca deben estar versionados en un repositorio de libro público.
PROHIBIDOS = [
    (re.compile(r"(^|/)\.env(\.|$)"), "archivo de credenciales (.env)"),
    (re.compile(r"recovery[-_ ]?codes", re.I), "códigos de recuperación de cuenta"),
    (re.compile(r"\.(pdf|epub|azw3|mobi|docx?|pptx?|xlsx?)$", re.I),
     "documento binario: los PDF/EPUB se generan en Releases y los insumos viven fuera del repositorio"),
]


def capitulos_del_indice():
    """Devuelve las rutas de src/SUMMARY.md en orden, sin duplicados."""
    texto = (SRC / "SUMMARY.md").read_text(encoding="utf-8")
    vistos, orden = set(), []
    for m in ENLACE_MD.finditer(texto):
        ruta = m.group(1)
        if ruta not in vistos:
            vistos.add(ruta)
            orden.append(ruta)
    return orden


def cmd_orden():
    for ruta in capitulos_del_indice():
        print(f"src/{ruta}")


def leer_metadatos():
    """Lectura mínima de metadatos.yml (claves simples 'clave: "valor"')."""
    datos = {}
    archivo = RAIZ / "metadatos.yml"
    if not archivo.exists():
        return datos
    for linea in archivo.read_text(encoding="utf-8").splitlines():
        m = re.match(r'^([a-z_-]+):\s*"?(.*?)"?\s*$', linea)
        if m and not linea.startswith((" ", "-", "#")):
            datos[m.group(1)] = m.group(2)
    return datos


def cmd_revisar():
    errores, avisos = [], []

    # 1. Índice y archivos coinciden
    indice = capitulos_del_indice()
    en_disco = sorted(p.name for p in SRC.glob("*.md") if p.name != "SUMMARY.md")
    for ruta in indice:
        if not (SRC / ruta).exists():
            errores.append(f"SUMMARY.md enlaza un archivo que no existe: src/{ruta}")
    for nombre in en_disco:
        if nombre not in indice:
            errores.append(f"src/{nombre} existe pero no está en SUMMARY.md: no aparecería ni en la web ni en el PDF")

    # 2. Enlaces internos entre capítulos
    for archivo in SRC.glob("*.md"):
        texto = archivo.read_text(encoding="utf-8")
        for m in ENLACE_MD.finditer(texto):
            destino = m.group(1)
            if "://" in destino:
                continue
            if not (archivo.parent / destino).exists():
                errores.append(f"{archivo.relative_to(RAIZ)}: enlace roto a '{destino}'")

    # 3. El título es el mismo en la web (book.toml) y en los ebooks (metadatos.yml)
    with open(RAIZ / "book.toml", "rb") as f:
        titulo_web = tomllib.load(f).get("book", {}).get("title", "")
    meta = leer_metadatos()
    if not meta:
        errores.append("falta metadatos.yml (título, subtítulo y autor de los ebooks)")
    elif meta.get("title") != titulo_web:
        errores.append(f"título distinto: book.toml='{titulo_web}' / metadatos.yml='{meta.get('title')}'")

    # 4. Nada prohibido versionado
    try:
        versionados = subprocess.run(
            ["git", "ls-files"], cwd=RAIZ, capture_output=True, text=True, check=True
        ).stdout.splitlines()
    except (OSError, subprocess.CalledProcessError):
        versionados = []
        avisos.append("no se pudo consultar git ls-files; se omitió la revisión de archivos prohibidos")
    for ruta in versionados:
        for patron, motivo in PROHIBIDOS:
            if patron.search(ruta):
                errores.append(f"'{ruta}' no debería estar en el repositorio: {motivo}")

    # 4b. La carpeta proceso/ (auditorías, pendientes, bitácora) es siempre privada:
    #     un repositorio público no puede contenerla.
    en_proceso = [r for r in versionados if r.startswith("proceso/")]
    if en_proceso:
        publico = os.environ.get("REPO_PUBLICO", "")
        msg = f"proceso/ está en el repositorio ({len(en_proceso)} archivo(s)); esa carpeta debe ser siempre privada"
        if publico == "true":
            errores.append(msg + " y este repositorio es PÚBLICO")
        elif publico != "false":
            avisos.append(msg + ": si este repositorio es o será público, sácala antes")

    # 5. Marcas de trabajo pendientes dentro del texto publicado (solo aviso)
    marca = re.compile(r"\[(AUTOR|PENDIENTE|TODO|REVISAR)\b[^\]]*\]")
    for archivo in sorted(SRC.glob("*.md")):
        n = len(marca.findall(archivo.read_text(encoding="utf-8")))
        if n:
            avisos.append(f"{archivo.relative_to(RAIZ)}: {n} marca(s) de trabajo pendiente ([AUTOR], [PENDIENTE]…)")

    for a in avisos:
        print(f"::warning::{a}" if "GITHUB_ACTIONS" in __import__("os").environ else f"AVISO: {a}")
    for e in errores:
        print(f"::error::{e}" if "GITHUB_ACTIONS" in __import__("os").environ else f"ERROR: {e}")
    print(f"\nRevisión editorial: {len(errores)} error(es), {len(avisos)} aviso(s).")
    return 1 if errores else 0


if __name__ == "__main__":
    accion = sys.argv[1] if len(sys.argv) > 1 else ""
    if accion == "orden":
        cmd_orden()
    elif accion == "revisar":
        sys.exit(cmd_revisar())
    else:
        print(__doc__)
        sys.exit(2)
