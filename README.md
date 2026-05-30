# Amazon Price Intelligence System

Price prediction and anomaly detection on Amazon India data using Machine Learning.

## Quick Start

```bash
pip install -r requirements.txt
python app.py
# Visit http://localhost:8000/docs
```

## What It Does

- **Price Prediction**: Predict product prices (R² = 0.84)
- **Anomaly Detection**: Catch fake discounts (124 detected)
- **Elasticity Analysis**: Price sensitivity by category (7.7% for appliances, 2.7% for laptops)

## Data

- 750 products tracked daily for 20 days
- 15,000 price & demand snapshots
- 3 categories: smartphones, laptops, home appliances

## Models

| Model | Algorithm | Performance |
|-------|-----------|-------------|
| Price Prediction | XGBoost | R² = 0.837 |
| Anomaly Detection | Isolation Forest | 124 anomalies caught |

## API Endpoints

- `POST /predict/price` - Predict product price
- `POST /detect/anomaly` - Flag suspicious products
- `GET /elasticity/{category}` - Get price elasticity
- `GET /dashboard/summary` - View statistics
- `GET /docs` - Interactive documentation

## Example

```bash
curl -X POST "http://localhost:8000/predict/price" \
  -H "Content-Type: application/json" \
  -d '{"brand": "Samsung", "category": "smartphones", "rating": 4.2, "reviews": 150, "discount_pct": 15}'
```

Response:
```json
{"predicted_price": 32456.78, "model_r2": 0.837, "confidence": "High"}
```

## Files

- `app.py` - FastAPI server
- `models/` - Trained ML models
- `amazon_analysis.db` - SQLite database
- `notebooks/` - Analysis code

## Key Findings

- 124 suspicious products with inflated discounts
- Category is strongest price driver (73.6%)
- Home appliances 2.8x more price-elastic than laptops

## Built With

- Python, XGBoost, scikit-learn
- FastAPI, Pydantic
- SQLite

## Deploy

```bash
# Render.com or Railway.app
# Set Start Command: uvicorn app:app --host 0.0.0.0 --port 8000
```