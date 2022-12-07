FROM python:3.9

RUN export POETRY_HOME=/opt/poetry && \
    export POETRY_VERSION=1.2.2 && \
    curl -sSL https://install.python-poetry.org | python3 - && \
    echo "export PATH=/opt/poetry/bin:$PATH" > /etc/profile.d/poetry.sh && \
    /opt/poetry/bin/poetry completions bash >> /etc/profile.d/poetry.sh

ENV WORKDIR=/opt/repository-settings
ENV CONFIGDIR=/etc/repository-settings

WORKDIR ${WORKDIR}
COPY * ${WORKDIR}/

# RUN pip install ghapi  \
#                 PyYaml

RUN mkdir -p ${CONFIGDIR}; \
    for file in ${WORKDIR}/*.yaml; do \
      ln -sf ${file} ${CONFIGDIR}/$(basename ${file}); \
    done

ENTRYPOINT ["python3", "/opt/repository-settings/main.py"]