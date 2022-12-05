FROM python:3.9

RUN pip install ghapi  \
                PyYaml

ENV WORKDIR=/opt/repository-settings
ENV CONFIGDIR=/etc/repository-settings

COPY * ${WORKDIR}/

RUN mkdir -p ${CONFIGDIR}; \
    for file in ${WORKDIR}/*.yaml; do \
      ln -sf ${file} ${CONFIGDIR}/$(basename ${file}); \
    done

ENTRYPOINT ["python3", "/opt/repository-settings/main.py"]