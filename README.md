# Real-Time Transaction Anomaly Detection

A streaming pipeline that ingests transactions in real time, flags suspicious ones using rule-based detection, stores results in PostgreSQL, and exposes the data through a REST API.

## Problem

Financial systems need to catch suspicious transactions as they happen, not hours later in a batch report. This project simulates that: transactions stream in continuously, get evaluated against a set of fraud-detection rules, and flagged transactions are stored with a clear, human-readable reason — not just a bare `"suspicious"` label.

## Architecture

```text
Transaction Generator
        │
        ▼
    Kafka Topic ("transactions")
        │
        ▼
   Kafka Consumer
        │
        ├──► Detection Rules (amount, velocity, odd-hour)
        │
        ▼
    PostgreSQL (transactions + anomalies tables)
        │
        ▼
   FastAPI (GET/POST endpoints)
```

The project has two ways to submit transactions:

* **Streaming path:** the generator continuously produces simulated transactions, which are sent through Kafka to the consumer.
* **API path:** transactions can also be submitted directly via `POST /transactions`, which is useful for manually creating and testing transaction records through the REST API.

The streaming path uses the same `detect_anomaly()` function for rule-based detection, providing a single source of truth for the current fraud-detection logic.

## Why these tools

* **Kafka** — real transaction systems need continuous ingestion rather than periodic batch jobs. Kafka decouples the producer (source of transactions) from the consumer (processing logic), while its offset-based consumption model allows unprocessed messages to be redelivered when appropriate.

* **PostgreSQL** — structured, relational storage fits this data well: accounts, transactions, and anomalies are naturally linked by foreign keys, and SQL makes querying transaction and anomaly data straightforward.

* **Docker** — Kafka and PostgreSQL run in containers. Kafka uses KRaft mode, so it does not require ZooKeeper. The infrastructure can be started with Docker Compose rather than requiring each service to be installed and configured manually.

* **FastAPI** — exposes the stored transaction and anomaly data over HTTP. Its Pydantic integration also validates incoming API request data before it reaches the database.

## Detection Rules

The current detection system is rule-based. An ML-based upgrade is planned as the next phase.

Current rules include:

* **Amount threshold** — flags transactions above a configured limit.
* **Velocity check** — a sliding window per account catches too many transactions within a short time period. This is implemented in plain Python, which is appropriate for the current data volume.
* **Odd-hour check** — flags transactions occurring during configured unusual hours.

Each flagged transaction stores a specific reason, or multiple reasons, rather than only a boolean flag.

For example:

```text
"unusually high amount, more than 4 transactions in 30s"
```

## Running the Project

### 1. Start the infrastructure

Start Kafka and PostgreSQL:

```bash
docker compose up -d
```

Check that the containers are running:

```bash
docker ps
```

You should see the Kafka and PostgreSQL containers running.

### 2. Set up the database

Run:

```bash
python schema.py
```

This creates the required database tables.

### 3. Start the streaming pipeline

Open two separate terminals.

Terminal 1 — transaction producer:

```bash
python transaction_generator.py
```

Terminal 2 — Kafka consumer:

```bash
python consumer.py
```

The consumer reads transactions from Kafka, applies the detection rules, and stores the results in PostgreSQL.

### 4. Start the API

Run:

```bash
uvicorn main:app --reload
```

The API will be available at:

```text
http://localhost:8000
```

Interactive Swagger documentation is available at:

```text
http://localhost:8000/docs
```

## API Endpoints

| Method | Endpoint          | Description                                         |
| ------ | ----------------- | --------------------------------------------------- |
| GET    | `/transactions`   | Returns the most recent transactions                |
| GET    | `/anomalies`      | Returns recent flagged anomalies with their reasons |
| GET    | `/anomalies/{id}` | Returns one specific anomaly                        |
| POST   | `/transactions`   | Creates a new transaction through the REST API      |

## Example: Flagged Transaction

A transaction stored as suspicious may have information such as:

```json
{
  "transaction_id": 42,
  "status": "suspicious",
  "risk_score": 0.70,
  "reason": "unusually high amount"
}
```

The exact fields returned depend on whether the transaction or anomaly endpoint is being queried.

## Engineering Notes

* **Kafka offset handling** — the consumer commits offsets only after successful processing. This reduces the risk of marking a transaction as processed before its database operation has completed. If processing fails before the commit, Kafka can redeliver the message when the consumer restarts.

* **Input validation** — API requests are validated using Pydantic before being inserted into PostgreSQL.

* **Relational schema** — transactions and anomalies are connected through foreign keys, allowing anomaly records to be queried together with their original transaction details.

* **Dockerized infrastructure** — Kafka and PostgreSQL run as separate containers managed through Docker Compose.

* **Rule-based detection** — the current system provides explainable detection reasons, making it clear why a transaction was flagged.

## What's Next

The next phase is to introduce machine learning into the fraud-detection pipeline.

Planned machine-learning work includes:

* Data collection and preparation
* Exploratory data analysis
* Feature engineering
* Train/test split
* Data preprocessing
* Logistic Regression as a baseline classifier
* Random Forest Classifier as the main model
* Evaluation using accuracy, precision, recall, F1-score, and confusion matrix
* Comparison of the ML model with the existing rule-based approach
* Model persistence and integration into the transaction pipeline

If rule-generated labels are used during experimentation, their limitations will also be considered, since the existing rules should not automatically be treated as perfect ground truth.

## Tech Stack
Python · Apache Kafka · PostgreSQL · SQLAlchemy · Docker · Docker Compose · FastAPI · Pydantic
