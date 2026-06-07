FROM python:3.14-slim

WORKDIR /app

COPY app/requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ app/

ENV FLASK_APP=app

EXPOSE 5000

COPY entrypoint.sh entrypoint.sh
RUN chmod +x entrypoint.sh

ENTRYPOINT ["sh", "entrypoint.sh"]
