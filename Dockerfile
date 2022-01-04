FROM python:3.7-slim

RUN apt-get update

RUN apt-get install -y \
    gdal-bin \
    sqlite3 \
    libsqlite3-mod-spatialite 

RUN mkdir -p /app
WORKDIR /app
ADD requirements.txt /app
RUN pip install -r requirements.txt
ADD main.py /app

VOLUME ["/app"]

CMD ["python", "main.py"]

