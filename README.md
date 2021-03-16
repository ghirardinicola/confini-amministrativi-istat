# Confini Amministrativi ISTAT

[![Data and open data on forum.italia.it](https://img.shields.io/badge/Forum-Dati%20e%20open%20data-blue.svg)](https://forum.italia.it/c/dati)
[![Confini Amministrativi ISTAT on forum.italia.it](https://img.shields.io/badge/Thread-%5BCall%20for%20ideas%5D%20Confini%20amministrativi%20ISTAT-blue.svg)](https://forum.italia.it/t/call-for-ideas-confini-amministrativi-istat/12224)

[![Join the #datascience channel](https://img.shields.io/badge/Slack%20channel-%23datascience-blue.svg?logo=slack)](https://developersitalia.slack.com/archives/C9B2NV3R6)
[![Get invited](https://slack.developers.italia.it/badge.svg)](https://slack.developers.italia.it/)

Collezione di utilities per facilitare il riuso dei dati ISTAT e ANPR sui confini amministrativi italiani. Per approfondimenti e discussione è aperto un [thread dedicato su Forum Italia](https://forum.italia.it/t/call-for-ideas-confini-amministrativi-istat/12224).

> Work in progress

## Contenuto del repository

Nel file `sources.json` ci sono i link a tutti gli shapefile rilasciati da ISTAT dal 2001 elencati in [questa tabella](https://www.istat.it/it/archivio/222527)
e il link all'[archivio dei comuni di ANPR](https://www.anpr.interno.it/portale/anpr-archivio-comuni.csv).

Lo script `main.py` scarica gli archivi zip dal sito ISTAT, li decomprime e li elabora in cartelle nominate con la data di rilascio: `YYYYMMDD/`.
Scarica anche il file di ANPR e lo arricchisce con i dati ISTAT contenuti negli shapefile.

Al momento sono supportati i seguenti formati di output:

* [ESRI shapefile](https://it.wikipedia.org/wiki/Shapefile) nella cartella `shp/` (formato originale)
* [Comma-separated values](https://it.wikipedia.org/wiki/Comma-separated_values) nella cartella `csv/`
* [Javascript Object Notation](https://it.wikipedia.org/wiki/JavaScript_Object_Notation) nella cartella `json/`
* [Geojson](https://it.wikipedia.org/wiki/GeoJSON) nella cartella `geojson/`
* [Geopackage](https://en.wikipedia.org/wiki/GeoPackage) nella cartella `geopkg/`
* [Topojson](https://it.wikipedia.org/wiki/GeoJSON#TopoJSON) nella cartella `topojson/`
* [Geobuf](https://github.com/pygeobuf/pygeobuf) nella cartella `geobuf/`

Il file di ANPR è quello originale arricchito delle denominazioni e dell'indicazione degli shapefile in cui i comuni sono presenti.

> Avvertenza: al momento è inserita nel repository solo la cartella di output risultante dall'esecuzione dell'applicazione relativa al file ISTAT più recente.

## Come eseguire l'applicazione

Si consiglia caldamente di usare la versione dockerizzata.

> Avvertenza: al momento vengono processati solo i primi due elementi di `sources.json` (gli shapefile istat più recenti disponibili).

> Avvertenza: al momento la conversione in topojson è commentata perché fornisce warning su alcuni poligoni

> Avvertenza: al momento la conversione in geobuf è commentata perché va in errore

### Versione dockerizzata

> Modalità consigliata

Clona questo repository con [Git](https://git-scm.com/): `git clone https://github.com/teamdigitale/confini-amministrativi-istat.git`.
Entra nella cartella appena creata: `cd confini-amministrativi-istat/`.

Effettua la build delle immagini: `docker build --target application -t italia-conf-amm-istat .` (puoi usare lo script `build.sh`).

Esegui un container per ogni tipologia di confine amministrativo: `docker run --env DIV=$DIV --volume=$PWD:/app italia-conf-amm-istat:latest`
con `$DIV` uguale a `ripartizioni-geografiche`, `regioni`, `unita-territoriali-sovracomunali` o `comuni` (puoi usare lo script `run.sh`).

L'esecuzione può richiedere diversi minuti, in output sono mostrati solo `ERROR` e `WARNING`.

### Esecuzione diretta

> Modalità altamente **sconsigliata**, le dipendenze indirette sono molte e si reggono su un equilibrio precario tra le versioni di ogni libreria.

Clona questo repository con [Git](https://git-scm.com/): `git clone https://github.com/teamdigitale/confini-amministrativi-istat.git`.
Entra nella cartella appena creata: `cd confini-amministrativi-istat/`.

Il file `requirements.txt` elenca tutte le dipendenze necessarie a eseguire l'applicazione.
Si consiglia di operare sempre in un ambiente isolato creando un apposito *virtual environment*.
Con [pipenv](https://pipenv.kennethreitz.org/en/latest/) è sufficiente entrare nel virtualenv con `pipenv shell` e la prima volta installare le dipendenze con `pipenv install`.

Infine, per eseguire l'applicazione: `python main.py`.

## Come contribuire

Ogni contributo è benvenuto, puoi aprire una issue oppure proporre una pull request, così come partecipare alla [discussione su Forum Italia](https://forum.italia.it/t/call-for-ideas-confini-amministrativi-istat/12224).
