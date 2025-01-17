import json
import logging
import os
import re
import subprocess
from io import BytesIO, StringIO
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import urlopen
from zipfile import ZipFile

import geobuf
import geopandas as gpd
import pandas as pd
import topojson
from simpledbf import Dbf5

OUTPUT_DIR = os.getenv("OUTPUT_DIR", "v1")
SOURCE_FILE = os.getenv("SOURCE_FILE", "sources.json")
SOURCE_NAME = os.getenv("SOURCE_NAME")

logging.basicConfig(level=logging.INFO)

# Apro il file con tutte le risorse
with open(SOURCE_FILE) as f:
    # Carico le risorse (JSON)
    sources = json.load(f)
    # Ciclo su tutte le risorse ISTAT
    for source in sources["istat"]:
        # Trasforma la lista di divisioni amministrative (comuni, province, ecc.) in un dizionario indicizzato
        source["divisions"] = {
            division["name"]: division for division in source.get("divisions", [])
        }
    # Trasforma la lista di divisioni amministrative (comuni, province, ecc.) in un dizionario indicizzato
    sources["ontopia"]["divisions"] = {
        division["name"]: division
        for division in sources["ontopia"].get("divisions", [])
    }

# ISTAT - Unità territoriali originali
logging.info("+++ ISTAT +++")
# Ciclo su tutte le risorse ISTAT
for source in sources["istat"]:  # noqa: C901

    if SOURCE_NAME and source["name"] != SOURCE_NAME:
        continue

    logging.info("Processing {}...".format(source["name"]))

    # ZIP - Zip of original shapefile
    # Cartella di output
    output_zip = Path(OUTPUT_DIR, source["name"], "zip")
    # Se non esiste...
    if not output_zip.exists():
        logging.info("-- zip")
        # ... la crea
        output_zip.mkdir(parents=True, exist_ok=True)
        # Scarico il file dal sito ISTAT
        # Workaround per certificate chain non completa di istat.it
        import ssl
        #output_shp.mkdir(parents=True, exist_ok=True) 
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

        with urlopen(source["url"], context=ctx) as res:
            # Lo leggo come archivio zip
            with ZipFile(BytesIO(res.read())) as zfile:
                # Ciclo su ogni file e cartella nell'archivio
                for zip_info in zfile.infolist():
                    # Elimino la cartella root dal percorso di ogni file e cartella
                    zip_info.filename = zip_info.filename.replace(source["rootdir"], "")
                    # Ciclo sulle divisioni amministrative
                    for division in source["divisions"].values():
                        # Rinomino le sottocartelle con il nome normalizzato delle divisioni
                        zip_info.filename = zip_info.filename.replace(
                            division["dirname"] + "/", division["name"] + "/"
                        ).replace(division["filename"] + ".", division["name"] + ".")
                    # Estraggo file e cartelle con un percorso non vuoto
                    if zip_info.filename:
                        zfile.extract(zip_info, output_zip)

    # SHP - Corrected shapefile
    # Cartella di output
    output_shp = Path(OUTPUT_DIR, source["name"], "shp")
    # Se non esiste...
    if not output_shp.exists():
        logging.info("-- shp")
        # ... la crea
        output_shp.mkdir(parents=True, exist_ok=True)
        # Ciclo su ogni suddivisione amministrativa
        for division in source["divisions"]:
            # Creazione cartella
            output_div = Path(output_shp, division)
            output_div.mkdir(parents=True, exist_ok=True)
            # Database spaziale temporaneo
            output_sqlite = output_div.with_suffix(".sqlite")
            # Crea il db sqlite e poi lo inizializza come db spaziale
            subprocess.run(
                [
                    "sqlite3",
                    output_sqlite,
                    "\n".join(
                        [
                            "SELECT load_extension('mod_spatialite');",
                            "SELECT InitSpatialMetadata(1);",
                        ]
                    ),
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            # Analisi dello shp originale
            subprocess.run(
                [
                    "sqlite3",
                    output_sqlite,
                    "\n".join(
                        [
                            "SELECT load_extension('mod_spatialite');",
                            # "-- importa shp come tabella virtuale",
                            "CREATE VIRTUAL TABLE \"{}\" USING VirtualShape('{}', UTF-8, 32632);".format(
                                division, Path(output_zip, division, division)
                            ),
                            # "-- crea tabella con output check geometrico",
                            'CREATE TABLE "{}_check" AS SELECT PKUID,GEOS_GetLastWarningMsg() msg,ST_AsText(GEOS_GetCriticalPointFromMsg()) punto FROM "{}" WHERE ST_IsValid(geometry) <> 1;'.format(
                                division, division
                            ),
                        ]
                    ),
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            # Conteggio degli errori rilevati
            errori = subprocess.check_output(
                [
                    "sqlite3",
                    output_sqlite,
                    "\n".join(['SELECT count(*) FROM "{}_check"'.format(division)]),
                ],
                stderr=subprocess.DEVNULL,
            )
            # Se ci sono errori crea nuova tabella con geometrie corrette
            logging.warning(
                "!!! Errori {}: {} geometrie corrette".format(division, int(errori))
            )
            if int(errori) > 0:
                subprocess.run(
                    [
                        "sqlite3",
                        output_sqlite,
                        "\n".join(
                            [
                                "SELECT load_extension('mod_spatialite');",
                                'CREATE table "{}_clean" AS SELECT * FROM "{}";'.format(
                                    division, division
                                ),
                                "SELECT RecoverGeometryColumn('{}_clean','geometry',32632,'MULTIPOLYGON','XY');".format(
                                    division
                                ),
                                'UPDATE "{}_clean" SET geometry = MakeValid(geometry) WHERE ST_IsValid(geometry) <> 1;'.format(
                                    division
                                ),
                            ]
                        ),
                    ],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            # Creazione shapefile con geometrie corrette
            subprocess.run(
                [
                    "ogr2ogr",
                    Path(output_div, division).with_suffix(".shp"),
                    output_sqlite,
                    "{}_clean".format(division),
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            # Pulizia file temporanei
            os.remove(output_sqlite)

    # CSV - Comma Separated Values
    # Cartella di output
    output_csv = Path(OUTPUT_DIR, source["name"], "csv")
    # Se non esiste...
    if not output_csv.exists():
        logging.info("-- csv")
        # ... la crea
        output_csv.mkdir(parents=True, exist_ok=True)
        # Ciclo su tutti i file dbf degli shapefile disponibili
        for dbf_filename in output_zip.glob("**/*.dbf"):
            # File di output (CSV)
            csv_filename = Path(
                output_csv, *dbf_filename.parts[3 if OUTPUT_DIR else 2 :]
            ).with_suffix(".csv")
            # Creo le eventuali sotto cartelle
            csv_filename.parent.mkdir(parents=True, exist_ok=True)
            # Carico il file dbf
            dbf = Dbf5(dbf_filename)
            dbf.columns = [c.upper() for c in dbf.columns]
            # Lo converto in CSV e lo salvo
            dbf.to_csv(csv_filename)
        # Ciclo su tutti i file CSV
        for csv_filename in output_csv.glob("**/*.csv"):
            # Carico il CSV come dataframe
            df = pd.read_csv(csv_filename, dtype=str)
            # Per ogni divisione amministrativa superiore a quella corrente
            for parent in (
                source["divisions"][division_id]
                for division_id in source["divisions"][csv_filename.stem].get(
                    "parents", []
                )
            ):
                # Carico il CSV come dataframe
                jdf = pd.read_csv(
                    Path(output_csv, parent["name"], parent["name"] + ".csv"), dtype=str
                )
                # Faccio il join selezionando le colonne che mi interessano
                df = pd.merge(
                    df,
                    jdf[[parent["key"]] + parent["fields"]],
                    on=parent["key"],
                    how="left",
                )
            # Sostituisco tutti i NaN con stringhe vuote
            df.fillna("", inplace=True)
            # Aggiungo l'URI di OntoPiA
            if "key" in sources["ontopia"]["divisions"][csv_filename.stem]:
                df["ONTOPIA"] = df[
                    sources["ontopia"]["divisions"][csv_filename.stem].get("key")
                ].apply(
                    lambda x: "{host:s}/{path:s}/{code:0{digits:d}d}".format(
                        host=sources["ontopia"].get("url", ""),
                        path=sources["ontopia"]["divisions"][csv_filename.stem].get(
                            "url", ""
                        ),
                        code=int(x),
                        digits=sources["ontopia"]["divisions"][csv_filename.stem].get(
                            "digits", 1
                        ),
                    )
                )
            # Salvo il file arricchito
            df.to_csv(
                csv_filename,
                index=False,
                columns=[
                    col
                    for col in df.columns
                    if "shape_" not in col.lower() and "pkuid" not in col.lower()
                ],
            )

        # JSON - Javascript Object Notation
        # Cartella di output
        output_json = Path(OUTPUT_DIR, source["name"], "json")
        # Se non esiste...
        if not output_json.exists():
            logging.info("-- json")
            # ... la crea
            output_json.mkdir(parents=True, exist_ok=True)
            # Ciclo su tutti i file csv
            for csv_filename in output_csv.glob("**/*.csv"):
                # Carico il CSV come dataframe
                df = pd.read_csv(csv_filename, dtype=str)
                # File di output (JSON)
                json_filename = Path(
                    output_json, *csv_filename.parts[3 if OUTPUT_DIR else 2 :]
                ).with_suffix(".json")
                # Creo le eventuali sotto cartelle
                json_filename.parent.mkdir(parents=True, exist_ok=True)
                # Salvo il file
                df.to_json(json_filename, orient="records")

    # Geojson + Topojson + Geobuf
    # Cartelle di output
    output_geojson = Path(OUTPUT_DIR, source["name"], "geojson")
    output_geopkg = Path(OUTPUT_DIR, source["name"], "geopkg")
    output_topojson = Path(OUTPUT_DIR, source["name"], "topojson")
    #output_geobuf = Path(OUTPUT_DIR, source["name"], "geobuf")

    # Le creo se non esistono
    output_geojson.mkdir(parents=True, exist_ok=True)
    output_geopkg.mkdir(parents=True, exist_ok=True)
    output_topojson.mkdir(parents=True, exist_ok=True)
    #output_geobuf.mkdir(parents=True, exist_ok=True)

    # Ciclo su tutti gli shapefile
    for shp_filename in output_shp.glob("**/*.shp"):

        # Carico gli shapefile come geodataframe
        gdf = gpd.read_file(shp_filename)

        # Geojson - https://geojson.org/
        # File di output
        geojson_filename = Path(
            output_geojson, *shp_filename.parts[3 if OUTPUT_DIR else 2 :]
        ).with_suffix(".json")
        # Se non esiste...
        if not geojson_filename.exists():
            logging.info("-- geojson")
            # ... ne creo il percorso
            geojson_filename.parent.mkdir(parents=True, exist_ok=True)
            # Converto in GEOJSON e salvo il file
            gdf.to_file(geojson_filename, driver="GeoJSON")

        # Geopackage - https://www.geopackage.org/
        # File di output
        geopkg_filename = Path(
            output_geopkg, *shp_filename.parts[3 if OUTPUT_DIR else 2 :]
        ).with_suffix(".gpkg")
        # Se non esiste...
        if not geopkg_filename.exists():
            logging.info("-- geopkg")
            # ... ne creo il percorso
            geopkg_filename.parent.mkdir(parents=True, exist_ok=True)
            # Converto in GEOJSON e salvo il file
            gdf.to_file(geopkg_filename, driver="GPKG")

        # # Topojson - https://github.com/topojson/topojson
        # # File di output
        # topojson_filename = Path(
        #     output_topojson, *shp_filename.parts[3 if OUTPUT_DIR else 2 :]
        # ).with_suffix(".json")
        # # Se non esiste...
        # if not topojson_filename.exists():
        #     logging.info("-- topojson")
        #     # ... ne creo il percorso
        #     topojson_filename.parent.mkdir(parents=True, exist_ok=True)
        #     # Carico e converto il GEOJSON in TOPOJSON
        #     tj = topojson.Topology(gdf, prequantize=False, topology=True)
        #     # Salvo il file
        #     with open(topojson_filename, "w") as f:
        #         f.write(tj.to_json())

    logging.info("End Processing {}...".format(source["name"]))

        # Geobuf - https://github.com/pygeobuf/pygeobuf
        # File di output
        # geobuf_filename = Path(output_geobuf, *shp_filename.parts[3 if OUTPUT_DIR else 2:]).with_suffix('.pbf')
        # Se non esiste...
        # if not geobuf_filename.exists() and geojson_filename.exists():
        #    logging.info("-- geobuf")
        # ... ne creo il percorso
        #    geobuf_filename.parent.mkdir(parents=True, exist_ok=True)
        # Carico il GEOJSON e lo converto in GEOBUF
        #    with open(geojson_filename) as f:
        #        pbf = geobuf.encode(json.load(f))
        # Salvo il file
        #    with open(geobuf_filename, 'wb') as f:
        #        f.write(pbf)

# Arricchisce anche i dati ANPR solo se si tratta di un'elaborazione completa
if not SOURCE_NAME:

    # ANPR - Archivio dei comuni
    logging.info("+++ ANPR +++")
    # Scarico il file dal permalink di ANPR
    with urlopen(sources["anpr"]["url"]) as res:

        # Nome del file
        csv_filename = Path(OUTPUT_DIR, sources["anpr"]["name"]).with_suffix(".csv")
        # Carico come dataframe
        try:
            df = pd.read_csv(StringIO(res.read().decode(sources["anpr"]["encoding"])), dtype=str)
        except pd.errors.ParserError as e:
            logging.warning(
                "!!! ANPR aggiornato non disponibile, uso la cache: {}".format(e)
            )
            try:
                df = pd.read_csv(
                    Path(os.path.basename(sources["anpr"]["url"])).with_suffix(".csv"),
                    encoding=sources["anpr"]["encoding"],
                    dtype=str,
                )
            except FileNotFoundError as e:
                logging.error("!!! ANPR non disponibile: {}".format(e))
                exit(1)

        # Ciclo su tutte le risorse istat
        for source in sources["istat"]:

            if SOURCE_NAME and source["name"] != SOURCE_NAME:
                continue

            # Divisione amministrativa utile per arricchire ANPR (quella comunale)
            division = source["divisions"].get(sources["anpr"]["division"]["name"])
            if division:

                logging.info("Processing {}...".format(source["name"]))

                # Carico i dati ISTAT come dataframe
                jdf = pd.read_csv(
                    Path(
                        OUTPUT_DIR,
                        source["name"],
                        "csv",
                        division["name"],
                        division["name"] + ".csv",
                    ),
                    dtype=str,
                )
                # Aggiungo un suffisso a tutte le colonne uguale al nome della fonte ISTAT (_YYYYMMDD)
                jdf.rename(
                    columns={
                        col: "{}_{}".format(col, source["name"]) for col in jdf.columns
                    },
                    inplace=True,
                )
                # Aggiungo una colonna GEO_YYYYMMDD con valore costante YYYYMMDD
                jdf["GEO_{}".format(source["name"])] = source["name"]
                # Faccio il join tra ANPR e fonte ISTAT selezionando solo le colonne che mi interessano
                df = pd.merge(
                    df,
                    jdf[
                        ["{}_{}".format(division["key"], source["name"])]
                        + [
                            "{}_{}".format(col, source["name"])
                            for col in division["fields"]
                        ]
                        + ["GEO_{}".format(source["name"])]
                    ],
                    left_on=sources["anpr"]["division"]["key"],
                    right_on="{}_{}".format(division["key"], source["name"]),
                    how="left",
                )
                # Elimino tutte le colonne duplicate (identici valori su tutte le righe)
                df = df.loc[:, ~df.T.duplicated(keep="first")]

        # Sostituisco tutti i NaN con stringhe vuote
        df.fillna("", inplace=True)
        # Concateno tutte le colonne GEO_YYYYMMDD in un'unica colonna GEO
        df["GEO"] = df[[col for col in df.columns if "GEO_" in col]].apply(
            lambda l: ",".join([str(x) for x in l if x]), axis=1
        )
        # Elimino le colonne temporanee GEO_YYYYMMDD
        df.drop(columns=[col for col in df.columns if "GEO_" in col], inplace=True)
        # Elimino i suffissi _YYYYMMDD da tutte le colonne
        df.rename(
            columns={col: re.sub(r"_\d+", "", col) for col in df.columns}, inplace=True
        )
        # Aggiungo la colonna di collegamento con OntoPiA
        df["ONTOPIA"] = df.apply(
            lambda row: "https://w3id.org/italia/controlled-vocabulary/territorial-classifications/cities/{}-({})".format(
                row["CODISTAT"], row["DATAISTITUZIONE"]
            ),
            axis=1,
        )
        # Salvo il file arricchito
        df.to_csv(csv_filename, index=False)
