# Real-Time Transaction Anomaly Detection

A streaming pipeline that ingests transactions in real time, flags suspicious ones using rule-based detection, stores results in PostgreSQL, and exposes the data through a REST API. The project is extended with a batch machine learning phase that adds two different ML approaches and compares their outputs against the existing rules.

## Problem

Financial systems need to identify suspicious transactions as they happen, not hours later in a batch report. This project simulates that workflow: transactions stream in continuously, get evaluated against a set of detection rules, and flagged transactions are stored with a clear, human-readable reason rather than just a bare `"suspicious"` label.

A second, offline phase then asks a different question: what additional signals can machine learning identify from historical transaction data, and how do those outputs compare with the existing rule engine?

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

```text
Batch ML Phase (Offline)

    transaction_features (feature engineering over transaction history)
        │
        ├──► Isolation Forest ──► ml_scores
        ├──► Logistic Regression ──► ml_scores_lr
        │
        ▼
    model_comparison (Rules vs Isolation Forest vs Logistic Regression)
        │
        ▼
   FastAPI ML endpoints (read-only)
```

The project has two ways to submit transactions:

* **Streaming path:** The generator continuously produces simulated transactions, which are sent through Kafka to the consumer.
* **API path:** Transactions can also be submitted directly via `POST /transactions`, useful for manually creating and testing transaction records.

The streaming path uses the same `detect_anomaly()` function for rule-based detection, providing a single source of truth for the current detection logic.

The ML phase runs separately and offline. It reads historical transactions already stored in PostgreSQL, builds features, trains both models, and writes results back to their own tables. It does not run inside the Kafka consumer and does not score a transaction in real time. A transaction only receives ML scores after the batch pipeline is re-run.

## Why These Tools

* **Kafka:** Provides continuous transaction ingestion and decouples the producer from the consumer that performs processing.
* **PostgreSQL:** Provides structured relational storage for accounts, transactions, anomalies, and ML results. It also acts as the integration point between the real-time rule engine and the offline ML phase.
* **Docker:** Kafka and PostgreSQL run in containers managed through Docker Compose. Kafka uses KRaft mode and does not require ZooKeeper.
* **FastAPI:** Exposes transaction, anomaly, and ML results over HTTP. Its Pydantic integration validates incoming API request data before it reaches the database.
* **scikit-learn:** Provides the Isolation Forest and Logistic Regression models, along with preprocessing and evaluation tools such as train/test splitting, scaling, precision, recall, F1, and ROC-AUC.

## Detection Rules

The real-time detection system is rule-based:

* **Amount threshold:** Flags transactions above a configured limit.
* **Velocity check:** A sliding window per account catches too many transactions within 30 seconds.
* **Odd-hour check:** Flags transactions occurring during configured unusual hours.

Each flagged transaction stores a specific reason, or multiple reasons, rather than only a boolean flag.

For example:

> `"unusually high amount, more than 4 transactions in 30s"`

## Machine Learning Phase

The ML phase is built on top of historical transaction data produced by the streaming system. It uses two different approaches:

* **Isolation Forest:** Unsupervised anomaly detection.
* **Logistic Regression:** Supervised classification using the rule engine's historical verdict as a proxy label.

### Feature Engineering

Features are built from raw transaction history stored in PostgreSQL, with explicit care to avoid leakage. Rolling and velocity features only consider transactions strictly before the current transaction.

| Feature                                               | Description                                                                                                           |
| ----------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------- |
| `amount`, `hour`, `day_of_week`, `is_weekend`         | Transaction amount and time-based features                                                                            |
| `transactions_last_30_sec`                            | Number of previous transactions for the account within 30 seconds                                                     |
| `transactions_last_5_min`, `transactions_last_1_hour` | Broader transaction velocity signals                                                                                  |
| `rolling_avg_amount`, `amount_deviation`              | An account's recent typical spending level and how far the current transaction deviates from it                       |
| `risk_score`                                          | The rule engine's computed risk score, with `0` for transactions without an anomaly record                            |
| `rule_flag`                                           | The rule engine's actual verdict, read directly from the transaction `status` rather than reconstructed independently |

### Isolation Forest (Unsupervised)

Isolation Forest is trained on the numerical transaction features without using `rule_flag` as a training feature. The model identifies observations that are unusual relative to the overall feature distribution.

The historical `rule_flag` rate is used only to set the `contamination` parameter, which represents the expected proportion of anomalies. It is not provided to the model as a feature.

**Results:**

* Transactions processed: **7,120**
* Contamination: **0.4250**
* Transactions flagged as anomalous: **3,026 / 7,120 (42.5%)**

The Isolation Forest therefore provides a separate anomaly signal rather than simply reproducing the rule engine's decision.

### Logistic Regression (Supervised Baseline)

Logistic Regression is trained using `rule_flag` as a proxy target. The dataset uses a stratified train/test split, and `StandardScaler` is fitted on the training data before transforming the test data.

**Evaluation results:**

| Metric    | Value |
| --------- | ----- |
| Precision | 1.000 |
| Recall    | 1.000 |
| F1        | 1.000 |
| ROC-AUC   | 1.000 |

**Top features by coefficient magnitude:**

| Feature                    | Coefficient |
| -------------------------- | ----------- |
| `risk_score`               | 6.362       |
| `transactions_last_30_sec` | 1.840       |
| `amount`                   | 1.135       |
| `amount_deviation`         | 1.058       |
| `hour`                     | -0.240      |
| `rolling_avg_amount`       | 0.221       |

> **Important interpretation:** These perfect evaluation metrics should not be interpreted as evidence that Logistic Regression is a perfect fraud detector. The model was trained using `rule_flag` as its target, and `risk_score` is itself produced by the rule engine. Therefore, strong agreement with the rules is partly expected by construction. The results demonstrate that the available features can reproduce the existing rule-based labels very effectively, rather than proving independent fraud-detection accuracy.

## Model Comparison

The outputs from Rules, Isolation Forest, and Logistic Regression are joined by transaction ID and compared pairwise.

| Comparison                             | Agreement Rate | Interpretation                                                                                    |
| -------------------------------------- | -------------- | ------------------------------------------------------------------------------------------------- |
| Rules ↔ Isolation Forest               | **66.8%**      | Most informative comparison because Isolation Forest does not use `rule_flag` as a training label |
| Rules ↔ Logistic Regression            | **100.0%**     | Expected to be high because Logistic Regression is trained on the rule-generated label            |
| Isolation Forest ↔ Logistic Regression | **66.8%**      | Shows where the unsupervised anomaly signal differs from the supervised rule-based baseline       |

### Disagreement Analysis

The rules and Isolation Forest disagreed on **2,366 transactions**:

* **1,183** transactions were flagged by Isolation Forest but not by the rules.
* **1,183** transactions were flagged by the rules but not by Isolation Forest.
* Logistic Regression disagreed with the rule label on **0 transactions**.

One example is transaction `5`:

| Field                           | Value       |
| ------------------------------- | ----------- |
| Transaction ID                  | `5`         |
| Account                         | `acc_001`   |
| Amount                          | `9,678.23`  |
| Rules                           | Not flagged |
| Isolation Forest                | Flagged     |
| Isolation Forest score          | `-0.226772` |
| Logistic Regression             | Not flagged |
| Logistic Regression probability | `0.000046`  |

This illustrates the different objectives of the two approaches. The rule engine applies explicit business conditions, while Isolation Forest identifies observations that appear unusual relative to the feature distribution.

These results should be treated as **anomaly-detection comparisons**, not confirmed fraud labels. A transaction flagged by a model is not automatically fraudulent.

## Running the Project

### 1. Start the infrastructure

```bash
docker compose up -d
docker ps
```

You should see the Kafka and PostgreSQL containers running.

### 2. Set up the database

```bash
python schema.py
```

### 3. Start the streaming pipeline

Open separate terminals.

**Terminal 1: Transaction producer**

```bash
python transaction_generator.py
```

**Terminal 2: Kafka consumer**

```bash
python consumer.py
```

The consumer reads transactions from Kafka, applies the detection rules, and stores the results in PostgreSQL.

### 4. Run the ML pipeline

Run the ML phase after enough transaction history exists:

```bash
python Ml/feature_table.py
python Ml/train_isolation_forest.py
python Ml/train_logistic_regression.py
python Ml/compare_models.py
```

Re-run this sequence whenever you want ML scores refreshed against newly streamed transactions. The ML phase does not update automatically as new transactions arrive.

### 5. Start the API

```bash
uvicorn main:app --reload
```

API available at:

```text
http://localhost:8000
```

Interactive Swagger documentation:

```text
http://localhost:8000/docs
```

## API Endpoints

| Method | Endpoint                  | Description                                                               |
| ------ | ------------------------- | ------------------------------------------------------------------------- |
| GET    | `/transactions`           | Returns the most recent transactions                                      |
| GET    | `/anomalies`              | Returns recent flagged anomalies with their reasons                       |
| GET    | `/anomalies/{id}`         | Returns one specific anomaly                                              |
| POST   | `/transactions`           | Creates a new transaction through the REST API                            |
| GET    | `/ml/isolation-forest`    | Returns Isolation Forest anomaly scores                                   |
| GET    | `/ml/logistic-regression` | Returns Logistic Regression predictions                                   |
| GET    | `/ml/comparison`          | Returns Rules, Isolation Forest, and Logistic Regression results together |

## Example: Flagged Transaction

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

* **Kafka offset handling:** The consumer commits offsets only after successful processing, reducing the risk of marking a transaction as processed before its database operation completes. If processing fails before the commit, Kafka can redeliver the message when the consumer restarts.
* **Input validation:** API requests are validated using Pydantic before being inserted into PostgreSQL.
* **Relational schema:** Transactions and anomalies are connected through foreign keys, allowing anomaly records to be queried together with their original transaction details.
* **Dockerized infrastructure:** Kafka and PostgreSQL run as separate containers managed through Docker Compose.
* **Rule-based detection:** The real-time system provides explainable detection reasons, making it clear why a transaction was flagged.
* **Decoupled ML phase:** The rule engine and ML pipeline share data through PostgreSQL rather than direct function calls. This separates the live transaction-processing path from the offline ML workflow.
* **Feature-engineering correction:** An early version of the feature pipeline used a 5-minute velocity window when the rule engine's relevant window was 30 seconds. This was corrected by using the transaction history and the rule engine's actual stored `status` for `rule_flag`, preventing the ML comparison label from being reconstructed with inconsistent logic.

## Tech Stack

**Python** · **Apache Kafka** · **PostgreSQL** · **SQLAlchemy** · **Docker** · **Docker Compose** · **FastAPI** · **Pydantic** · **scikit-learn**
