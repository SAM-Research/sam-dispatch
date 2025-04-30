FROM python:3.12-slim

WORKDIR /
COPY . .
RUN pip install .

ENTRYPOINT [ "sam-dispatch" ]