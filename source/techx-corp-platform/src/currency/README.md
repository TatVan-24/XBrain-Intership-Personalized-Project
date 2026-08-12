# Currency Service

The Currency Service does the conversion from one currency to another.

## Supported currencies and rates

The service uses 151 EUR-based reference rates pinned for deterministic local demos. The snapshot
comes from the official Banca d'Italia exchange-rate API and is dated 2026-08-10. It includes VND
at 30,252 dong per EUR. These values are for product demonstration and testing only, not for settling
real financial transactions. Update `src/currency/src/currency_rates.inc` when a new snapshot is required.
It is a C++ based service.

## Building docker image

To build the currency service, run the following from root directory
of techx-corp

```sh
docker compose build currency
```

## Run the service

Execute the below command to run the service.

```sh
docker compose up currency
```

## Run the client

currencyclient is a sample client which sends some request to currency
service. To run the client, execute the below command.

```sh
docker exec -it <container_name> currencyclient 7000
```

`7000` is port where currency listens to.
