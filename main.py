from datetime import datetime

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, insert

from schema import engine, transactions, anomalies
 
app = FastAPI(title="Fraud Detection API")
 
 
@app.get("/transactions")
def get_transactions(limit: int = 20):
    """Return the most recent transactions."""
    with engine.connect() as conn:
        query = select(transactions).order_by(transactions.c.timestamp.desc()).limit(limit)
        rows = conn.execute(query).mappings().all()
        return {"count": len(rows), "transactions": [dict(row) for row in rows]}
 
 
@app.get("/anomalies")
def get_anomalies(limit: int = 20):
    """Return the most recent flagged anomalies, joined with their transaction details."""
    with engine.connect() as conn:
        query = (
            select(
                anomalies.c.id,
                anomalies.c.transaction_id,
                anomalies.c.risk_score,
                anomalies.c.reason,
                anomalies.c.detected_at,
                transactions.c.account_id,
                transactions.c.amount,
                transactions.c.merchant,
                transactions.c.location,
            )
            .join(transactions, transactions.c.transaction_id == anomalies.c.transaction_id)
            .order_by(anomalies.c.detected_at.desc())
            .limit(limit)
        )
        rows = conn.execute(query).mappings().all()
        return {"count": len(rows), "anomalies": [dict(row) for row in rows]}
 
 
@app.get("/anomalies/{anomaly_id}")
def get_anomaly_by_id(anomaly_id: int):
    """Return one specific anomaly by its id."""
    with engine.connect() as conn:
        query = (
            select(
                anomalies.c.id,
                anomalies.c.transaction_id,
                anomalies.c.risk_score,
                anomalies.c.reason,
                anomalies.c.detected_at,
                transactions.c.account_id,
                transactions.c.amount,
                transactions.c.merchant,
                transactions.c.location,
            )
            .join(transactions, transactions.c.transaction_id == anomalies.c.transaction_id)
            .where(anomalies.c.id == anomaly_id)
        )
        row = conn.execute(query).mappings().first()
        if row is None:
            raise HTTPException(status_code=404, detail="Anomaly not found")
        return dict(row)

class TransactionCreate(BaseModel):
    account_id: str
    amount: float
    location: str
    merchant: str


class TransactionResponse(BaseModel):
    transaction_id: int
    account_id: str
    amount: float
    location: str
    merchant: str
    status: str
    timestamp: datetime
@app.post("/transactions", response_model=TransactionResponse)
def create_transaction(transaction: TransactionCreate):

    query = (
        insert(transactions)
        .values(
            account_id=transaction.account_id,
            amount=transaction.amount,
            location=transaction.location,
            merchant=transaction.merchant,
            status="normal"
        )
        .returning(
            transactions.c.transaction_id,
            transactions.c.account_id,
            transactions.c.amount,
            transactions.c.location,
            transactions.c.merchant,
            transactions.c.status,
            transactions.c.timestamp
        )
    )

    with engine.begin() as conn:
        row = conn.execute(query).mappings().first()

    return dict(row)