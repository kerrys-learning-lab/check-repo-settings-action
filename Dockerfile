FROM python:3.13

RUN export POETRY_HOME=/opt/poetry && \
    export POETRY_VERSION=1.3.0 && \
    curl -sSL https://install.python-poetry.org | python3 - && \
    install -o root -g root -m 555 /opt/poetry/bin/poetry /usr/local/bin/poetry && \
    /opt/poetry/bin/poetry completions bash >> /etc/profile.d/poetry.sh

ENV WORKDIR=/opt/repository-settings
ENV CONFIGDIR=/etc/repository-settings
ENV POETRY_VIRTUALENVS_CREATE=false

WORKDIR ${WORKDIR}
COPY * ${WORKDIR}/

RUN /opt/poetry/bin/poetry install --only=main

RUN mkdir -p ${CONFIGDIR}; \
    for file in ${WORKDIR}/*.yaml; do \
      ln -sf ${file} ${CONFIGDIR}/$(basename ${file}); \
    done

ENTRYPOINT ["/opt/repository-settings/main.py"]
CMD ["--verbose"]
