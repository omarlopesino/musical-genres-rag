ARG PGVECTOR_VERSION=pg18
FROM pgvector/pgvector:${PGVECTOR_VERSION}

ADD https://github.com/timescale/pg_textsearch.git#v1.3.1 /tmp/pg_textsearch

RUN apt-get update && \
  apt-mark hold locales && \
  apt-get install -y --no-install-recommends build-essential postgresql-server-dev-$PG_MAJOR && \
  cd /tmp/pg_textsearch && \
  make && \
  make install && \
  rm -rf /tmp/pg_textsearch && \
  apt-get remove -y build-essential postgresql-server-dev-$PG_MAJOR && \
  apt-get autoremove -y && \
  apt-mark unhold locales && \
  rm -rf /var/lib/apt/lists/*

CMD ["postgres", "-c", "shared_preload_libraries=pg_textsearch"]
