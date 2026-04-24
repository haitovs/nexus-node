ARG PYTHON_VERSION=3.12

FROM python:$PYTHON_VERSION-slim AS build

ENV PYTHONUNBUFFERED=1
WORKDIR /code

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential curl unzip gcc python3-dev \
    && LATEST=$(curl -sL https://api.github.com/repos/XTLS/Xray-core/releases/latest | grep '"tag_name"' | cut -d'"' -f4) \
    && curl -L "https://github.com/XTLS/Xray-core/releases/download/${LATEST}/Xray-linux-64.zip" -o /tmp/xray.zip \
    && unzip /tmp/xray.zip -d /usr/local/bin xray \
    && unzip /tmp/xray.zip -d /usr/local/share/xray geoip.dat geosite.dat \
    && chmod +x /usr/local/bin/xray \
    && rm /tmp/xray.zip \
    # Hysteria2 — apernet/hysteria app binary. Pinned to a known-good
    # release; bump here to upgrade fleet-wide. See
    # docs/HYSTERIA2_INTEGRATION.md in the panel repo.
    && HY2_VERSION="app/v2.8.1" \
    && curl -fsSL "https://github.com/apernet/hysteria/releases/download/${HY2_VERSION}/hysteria-linux-amd64" \
        -o /usr/local/bin/hysteria \
    && chmod +x /usr/local/bin/hysteria \
    && rm -rf /var/lib/apt/lists/*

COPY ./requirements.txt /code/
RUN pip install --no-cache-dir --upgrade -r /code/requirements.txt

FROM python:$PYTHON_VERSION-slim

ENV PYTHON_LIB_PATH=/usr/local/lib/python${PYTHON_VERSION%.*}/site-packages
WORKDIR /code

RUN rm -rf $PYTHON_LIB_PATH/*

COPY --from=build $PYTHON_LIB_PATH $PYTHON_LIB_PATH
COPY --from=build /usr/local/bin /usr/local/bin
COPY --from=build /usr/local/share/xray /usr/local/share/xray
COPY . /code

CMD ["python", "main.py"]
