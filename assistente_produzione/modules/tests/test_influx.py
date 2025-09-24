
from influxdb_client import InfluxDBClient

token = "tecnologic's Token"
org = "tecnologic"
url = "http://localhost:8086"
username = "tecnologic"  # Sostituisci con il tuo username
password = "Tecnologic2019!!"  # Sostituisci con la tua password


#client = InfluxDBClient(url=url, token=token, org=org)
# Autenticazione con username e password per ottenere un token
client = InfluxDBClient(url=url, username=username, password=password, org=org)

buckets = client.buckets_api().find_buckets()
for bucket in buckets.buckets:
    print(bucket.name)
    # Lettura dei dati da un bucket specifico
    query_api = client.query_api()
    query = f'from(bucket: "{bucket.name}") |> range(start: -3mo)'  # Sostituisci "my-bucket" con il nome reale
    result = query_api.query(org=org, query=query)

    # Stampa dei risultati

    for table in result:
        for record in table.records:
            print(f"Table: {record.table} Time: {record.get_time()}, Field: {record.get_field()}, Value: {record.get_value()}")

# Chiudi la connessione
client.close()