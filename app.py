
from fastapi import FastAPI
from pydantic import BaseModel
import joblib
import numpy as np
import json
import uvicorn

# Create FastAPI app
app = FastAPI(
    title="Amazon Price Intelligence API",
    description="ML models for price prediction and anomaly detection",
    version="1.0.0"
)

# Load trained models (from Stage 3)
price_model = joblib.load("models/price_model.pkl")
anomaly_model = joblib.load("models/anomaly_model.pkl")
le_brand = joblib.load("models/le_brand.pkl")
le_category = joblib.load("models/le_category.pkl")

# Store elasticity results from SQL analysis (Stage 2)
elasticity_data = {
    "home_appliances": {
        "coefficient": 0.77,
        "interpretation": "10% price drop = 7.7% demand increase",
        "products_analyzed": 44
    },
    "laptops": {
        "coefficient": 0.27,
        "interpretation": "10% price drop = 2.7% demand increase",
        "products_analyzed": 6
    },
    "smartphones": {
        "coefficient": None,
        "interpretation": "Insufficient products with >5% price drops",
        "products_analyzed": 4
    }
}

# Project statistics
project_stats = {
    "total_products": 750,
    "total_snapshots": 15000,
    "days_tracked": 20,
    "categories": ["smartphones", "laptops", "home_appliances"],
    "data_collection": "2026-04-26 to 2026-05-27",
    "brands": 20
}



#BLOCK 2: REQUEST/RESPONSE SCHEMAS (Data Validation)


# What format does the user send data in?
# What format do we send back?
# Pydantic ensures data is valid before processing

class PricePredictionRequest(BaseModel):
    """Input for price prediction"""
    brand: str                    # e.g., "Samsung"
    category: str                 # e.g., "smartphones"
    rating: float                 # e.g., 4.2
    reviews: int                  # e.g., 150
    discount_pct: float           # e.g., 15.0

    class Config:
        example = {
            "brand": "Samsung",
            "category": "smartphones",
            "rating": 4.2,
            "reviews": 150,
            "discount_pct": 15.0
        }


class PricePredictionResponse(BaseModel):
    """Output from price prediction"""
    predicted_price: float
    model_r2: float
    confidence: str


class AnomalyDetectionRequest(BaseModel):
    """Input for anomaly detection"""
    price: float                  # e.g., 32500
    mrp: float                    # e.g., 45000
    discount_pct: float           # e.g., 27.8
    reviews: int                  # e.g., 500
    rating: float                 # e.g., 4.1

    class Config:
        example = {
            "price": 32500,
            "mrp": 45000,
            "discount_pct": 27.8,
            "reviews": 500,
            "rating": 4.1
        }


class AnomalyDetectionResponse(BaseModel):
    """Output from anomaly detection"""
    is_anomaly: bool
    anomaly_score: float
    interpretation: str


class ElasticityResponse(BaseModel):
    """Output for elasticity lookup"""
    category: str
    elasticity_coefficient: float
    interpretation: str
    products_analyzed: int
    confidence: str


class DashboardResponse(BaseModel):
    """Dashboard summary"""
    data_stats: dict
    model_performance: dict
    key_insights: list


# ENDPOINT 1 - PRICE PREDICTION


@app.post("/predict/price", response_model=PricePredictionResponse)
def predict_price(request: PricePredictionRequest):
    """
    Predict a product's price using XGBoost model.
    
    Input: brand, category, rating, reviews, discount_pct
    Output: predicted_price, model_r2, confidence
    """
    
    try:
        # Encode categorical variables
        brand_encoded = le_brand.transform([request.brand])[0]
        category_encoded = le_category.transform([request.category])[0]
        
        # Prepare features in same order as training
        features = np.array([[
            brand_encoded,
            category_encoded,
            request.rating,
            request.reviews,
            request.discount_pct,
            0  # day_of_week (default to 0)
        ]])
        
        # Predict
        predicted_price = float(price_model.predict(features)[0])
        
        # Model R² from training
        model_r2 = 0.837
        
        # Determine confidence level
        if model_r2 > 0.8:
            confidence = "High"
        elif model_r2 > 0.6:
            confidence = "Medium"
        else:
            confidence = "Low"
        
        return PricePredictionResponse(
            predicted_price=round(predicted_price, 2),
            model_r2=model_r2,
            confidence=confidence
        )
    
    except Exception as e:
        return {"error": f"Price prediction failed: {str(e)}"}



#ENDPOINT 2 - ANOMALY DETECTION


@app.post("/detect/anomaly", response_model=AnomalyDetectionResponse)
def detect_anomaly(request: AnomalyDetectionRequest):
    """
    Detect suspicious pricing patterns using Isolation Forest.
    
    Input: price, mrp, discount_pct, reviews, rating
    Output: is_anomaly (True/False), anomaly_score, interpretation
    """
    
    try:
        # Prepare features
        features = np.array([[
            request.price,
            request.mrp,
            request.discount_pct,
            request.reviews,
            request.rating
        ]])
        
        # Get anomaly predictions
        anomaly_prediction = anomaly_model.predict(features)[0]  # -1 = anomaly, 1 = normal
        anomaly_score = float(anomaly_model.score_samples(features)[0])
        
        # Convert to boolean
        is_anomaly = anomaly_prediction == -1
        
        # Generate interpretation
        if is_anomaly:
            price_range = request.mrp - request.price
            if request.discount_pct > 30 and price_range < 500:
                interpretation = f"High discount ({request.discount_pct}%) but stable price (₹{price_range} range). Likely MRP inflation."
            else:
                interpretation = "Unusual pricing pattern detected."
        else:
            interpretation = "Normal pricing pattern."
        
        return AnomalyDetectionResponse(
            is_anomaly=is_anomaly,
            anomaly_score=round(anomaly_score, 4),
            interpretation=interpretation
        )
    
    except Exception as e:
        return {"error": f"Anomaly detection failed: {str(e)}"}


# ENDPOINT 3 - ELASTICITY LOOKUP


@app.get("/elasticity/{category}", response_model=ElasticityResponse)
def get_elasticity(category: str):
    """
    Get price elasticity for a category.
    
    Input: category (smartphones, laptops, home_appliances)
    Output: elasticity coefficient and interpretation
    """
    
    # Normalize category name
    category = category.lower()
    
    # Check if category exists
    if category not in elasticity_data:
        return {"error": f"Category '{category}' not found. Use: smartphones, laptops, home_appliances"}
    
    # Get elasticity
    elasticity_info = elasticity_data[category]
    
    # Determine confidence
    if elasticity_info["products_analyzed"] > 20:
        confidence = "High"
    elif elasticity_info["products_analyzed"] > 5:
        confidence = "Medium"
    else:
        confidence = "Low"
    
    return ElasticityResponse(
        category=category,
        elasticity_coefficient=elasticity_info["coefficient"] or 0,
        interpretation=elasticity_info["interpretation"],
        products_analyzed=elasticity_info["products_analyzed"],
        confidence=confidence
    )


#ENDPOINT 4 - DASHBOARD SUMMARY


@app.get("/dashboard/summary", response_model=DashboardResponse)
def get_dashboard():
    """
    Get project statistics and model performance summary.
    
    No input required.
    Output: data stats, model performance, key insights
    """
    
    dashboard_response = DashboardResponse(
        data_stats={
            "total_products": project_stats["total_products"],
            "total_snapshots": project_stats["total_snapshots"],
            "days_tracked": project_stats["days_tracked"],
            "categories": project_stats["categories"],
            "data_collection_period": project_stats["data_collection"]
        },
        model_performance={
            "price_prediction": {
                "algorithm": "XGBoost",
                "r2_score": 0.837,
                "rmse": "₹28,058",
                "mae": "₹13,638",
                "status": "Production Ready"
            },
            "anomaly_detection": {
                "algorithm": "Isolation Forest",
                "anomalies_found": 124,
                "contamination_rate": "4.98%",
                "recall": "100% (validated against SQL)",
                "status": "Production Ready"
            },
            "elasticity": {
                "home_appliances": 0.77,
                "laptops": 0.27,
                "smartphones": "Insufficient samples"
            }
        },
        key_insights=[
            "124 suspicious products detected (high discount, stable price)",
            "Category is strongest price driver (73.6% feature importance)",
            "Home appliances 2.8x more price-elastic than laptops",
            "Top product gained 5,286 reviews in 20 days (strong demand signal)",
            "Price volatility peaks in laptop category (₹111k range)"
        ]
    )
    
    return dashboard_response


# ROOT ENDPOINT & RUN SERVER


@app.get("/")
def root():
    """Welcome message"""
    return {
        "message": "Amazon Price Intelligence API",
        "endpoints": {
            "/docs": "Interactive API documentation (Swagger UI)",
            "/predict/price": "POST - Predict product price",
            "/detect/anomaly": "POST - Detect suspicious pricing",
            "/elasticity/{category}": "GET - Get price elasticity",
            "/dashboard/summary": "GET - View project statistics"
        },
        "example_category": "smartphones, laptops, home_appliances"
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
