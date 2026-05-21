MODEL_VERSION  = "V1.0.0"
from fastapi import FastAPI
from google.cloud import bigquery
from datetime import datetime
import random
from google.cloud import aiplatform
import google.generativeai as genai
from datetime import datetime


#3 Connecting to googgle Gemini
genai.configure(
    api_key="AIzaSyAkJtVtpeCNcEhJ_wxPAR3CGnFbZr0ZAOw"
)
model = genai.GenerativeModel(
    "models/gemini-2.5-flash"
)

app = FastAPI()
client = bigquery.Client()


@app.get("/")
def home():
    return {"message": "Pricing Agent is running"}




##the conversational AI endpoint
@app.get("/chat_explain")

def chat_explain(
    stock_code: str,
    question: str
):

    query = f"""
    SELECT

        StockCode,
        recommended_price,
        predicted_profit,
        predicted_units

    FROM
    `pricing-optimization-agent.pricing_agent_dev.pricing_outcomes_log`

    WHERE StockCode = '{stock_code}'

    ORDER BY timestamp DESC

    LIMIT 1
    """

    df = client.query(query).to_dataframe()

    if df.empty:

        return {
            "message": "No pricing data found"
        }

    row = df.iloc[0]

    context = f"""

    SKU: {row['StockCode']}

    Recommended Price:
    {row['recommended_price']}

    Predicted Profit:
    {row['predicted_profit']}

    Predicted Units:
    {row['predicted_units']}

    """

    prompt = f"""

    You are an AI pricing optimization assistant.

    Here is the pricing context:

    {context}

    User Question:
    {question}

    Give a concise business explanation.
    """

    response = model.generate_content(
        prompt
    )

    return {

        "stock_code": stock_code,

        "question": question,

        "context": context,

        "response": response.text
    }



@app.get("/recommend")
def recommend_price(stock_code: str):
    
    model_query = """
    SELECT
        model_version,
        endpoint_id

    FROM
    `pricing-optimization-agent.pricing_agent_dev.model_registry`

    WHERE model_role = 'CHAMPION'

    LIMIT 1
    """

    model_df = client.query(
        model_query
    ).to_dataframe()

    active_endpoint_id = model_df.iloc[0]["endpoint_id"]


    query = """
    SELECT
        StockCode,
        start_week,
        current_price,
        confidence_score,
        risk_score,
        lag_1_units,
        lag_2_units,
        rolling_4_wk_units,
        rolling_4_wk_price,
        inventory_level,
        current_price * 1.05 AS competitor_price
        

        FROM `pricing-optimization-agent.pricing_agent_dev.feature_store`
    WHERE StockCode = @stock_code
    ORDER BY start_week DESC
    LIMIT 1
    """

    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("stock_code", "STRING", stock_code)
        ]
    )

    results = client.query(
        query,
        job_config=job_config
    ).to_dataframe()

    if results.empty:
        return {"message": "No recommendation found"}  
    row = results.iloc[0]

    best_price = None
    best_profit = -999999
    best_units = None
    best_revenue = None

    profit_weight = 0.60
    revenue_weight = 0.25
    inventory_weight = 0.15

    current_price = float(row["current_price"])
    inventory_level = int(row["inventory_level"])
    competitor_price = float(row["competitor_price"])
    current_month = datetime.now().month   
    MAX_INCREASE_PCT = 0.20
    MAX_DECREASE_PCT = 0.10


    ##Adding inventory, seasonality and price rules
    if inventory_level < 20:
        MAX_INCREASE_PCT = 0.30
    elif inventory_level > 200:
        MAX_DECREASE_PCT = 0.25
    # Holiday season
    if current_month in [11, 12]:
        MAX_INCREASE_PCT += 0.10
    # Slow season discounts
    elif current_month in [1, 2]:
        MAX_DECREASE_PCT += 0.10    

   # Dynamic Risk control: If confidence is low, be more conservative
    HIGH_RISK = False
    if abs(
            float(row["lag_1_units"])
            -
            float(row["lag_2_units"])
        ) > 50:

            HIGH_RISK = True
    if HIGH_RISK:

        MAX_INCREASE_PCT = min(
            MAX_INCREASE_PCT,
            0.10
        )


    min_price = current_price * (1 - MAX_DECREASE_PCT)
    max_price = current_price * (1 + MAX_INCREASE_PCT)
    MIN_MARGIN = 0.25
    # Competitor price constraint
    MAX_COMPETITOR_PREMIUM = 0.15
    competitor_max_price = (
        competitor_price *
        (1 + MAX_COMPETITOR_PREMIUM)
    )
    max_price = min(
        max_price,
        competitor_max_price
    )
    
    candidate_prices = [
        round(min_price + i * 0.50, 2)
        for i in range(int((max_price - min_price) / 0.50) + 1)
]


    # Vertex endpoint
    ENDPOINT_ID = active_endpoint_id

    endpoint = aiplatform.Endpoint(
        f"projects/300192014618/locations/us-central1/endpoints/{ENDPOINT_ID}"
    )


    best_score = -999999

    for price in candidate_prices:

        prediction = endpoint.predict(
            instances=[
                [
                    price,
                    float(row["lag_1_units"]),
                    float(row["lag_2_units"]),
                    float(row["rolling_4_wk_units"]),
                    float(row["rolling_4_wk_price"])
                ]
            ]
        )

        predicted_units = prediction.predictions[0]

        predicted_revenue = predicted_units * price

        estimated_cost = price * 0.6

        predicted_profit = (
            predicted_units *
            (price - estimated_cost)
        )

        inventory_turnover_score = predicted_units / max(inventory_level, 1)
        objective_score = (
            profit_weight * predicted_profit
            + revenue_weight * predicted_revenue
            + inventory_weight * inventory_turnover_score
        )

        margin_pct = (
            (price - estimated_cost)
            / price
        )

        if margin_pct < MIN_MARGIN:
            continue

        if objective_score > best_score:
            best_score = objective_score

            best_profit = predicted_profit
            best_price = price
            best_units = predicted_units
            best_revenue = predicted_revenue


        


       # Advanced experiment assignment

    customer_segment = "HIGH_VALUE"

    region = "US"

    if customer_segment == "HIGH_VALUE":

        group = "A"
        final_price = best_price

    else:

        group = "B"
        final_price = row["current_price"]

        # price change
        try:
            price_change_pct = (
                (best_price - row["current_price"])
                / row["current_price"]
            )
        except Exception:
            price_change_pct = None

    ## logging . Experiment asigmnet trackin/Casual metabdata
    experiment_rows = [
        {
            "assignment_time": datetime.utcnow().isoformat(),

            "experiment_id": "pricing_exp_v1",

            "stock_code": str(row["StockCode"]),

            "customer_segment": customer_segment,

            "region": region,

            "ab_group": group,

            "model_version": MODEL_VERSION
        }
    ]

    experiment_table = (
        "pricing-optimization-agent.pricing_agent_dev.experiment_assignments"
    )

    experiment_errors = client.insert_rows_json(
        experiment_table,
        experiment_rows
    )

    if experiment_errors:
        print("Experiment logging error:", experiment_errors)

    # logging production prediction/performance log
    rows_to_insert = [
        {
            "timestamp": datetime.utcnow().isoformat(),
            "StockCode": str(row["StockCode"]),
            "recommended_price": best_price,
            "actual_price": None,
            "predicted_units": best_units,
            "predicted_revenue": best_revenue,
            "predicted_profit": best_profit,
            "actual_profit": None,
            "actual_units": None,
            "ab_group": group,
            "model_version": MODEL_VERSION
        }
    ]

    table_id = "pricing-optimization-agent.pricing_agent_dev.pricing_outcomes_log"

    errors = client.insert_rows_json(
        table_id,
        rows_to_insert
    )

    if errors:
        print("Logging error:", errors)

    prediction_log_rows = [
        {
            "prediction_time": datetime.utcnow().isoformat(),
            "stock_code": str(row["StockCode"]),
            "current_price": str(row["current_price"]),
            "recommended_price": str(best_price),
            "predicted_units_sold": None,
            "predicted_revenue": None,
            "predicted_units": predicted_units,
            "predicted_revenue": predicted_revenue,
            "predicted_profit": predicted_profit
        }
    ]

    prediction_log_table = (
        "pricing-optimization-agent.pricing_agent_dev.prediction_logs"
    )

    prediction_errors = client.insert_rows_json(
        prediction_log_table,
        prediction_log_rows
    )

    if prediction_errors:
        print("Prediction logging error:", prediction_errors)
    
    ## audit loggging for compliance and traceability
    audit_rows = [
        {
            "audit_time": datetime.utcnow().isoformat(),

            "stock_code": str(row["StockCode"]),

            "model_version": MODEL_VERSION,

            "current_price": float(row["current_price"]),

            "recommended_price": float(best_price),

            "predicted_profit": float(best_profit),

            "confidence_score": float(row["confidence_score"]),

            "risk_score": float(row["risk_score"]),

            "approval_status": "AUTO_APPROVED",

            "triggered_rules": "margin_protection,multi_objective_optimization,inventory_constraints",

            "deployed_by": "pricing_agent",

            "rollback_reference": "v1_pricing_model"
        }
    ]

    audit_table = (
        "pricing-optimization-agent.pricing_agent_dev.audit_trail"
    )

    audit_errors = client.insert_rows_json(
        audit_table,
        audit_rows
    )

    if audit_errors:
        print("Audit logging error:", audit_errors)



    return {
        "stock_code": str(row["StockCode"]),
        "ab_group": str(group),
        "final_price": str(final_price),
        "recommended_price": str(best_price),
        "current_price": str(row["current_price"]),
        "price_change_pct": str(price_change_pct),
        "predicted_units": predicted_units,
        "predicted_revenue": predicted_revenue,
        "predicted_profit": predicted_profit,
        "confidence_score": str(row["confidence_score"]),
        "risk_score": str(row["risk_score"]),
        
    }


@app.get("/scenario_simulation")
def scenario_simulation(

    stock_code: str,

    demand_multiplier: float = 1.0,

    inventory_multiplier: float = 1.0,

    competitor_price_multiplier: float = 1.0
):

    current_price = 10.0

    inventory_level = 100

    competitor_price = current_price * 1.05

    simulated_inventory = (
        inventory_level *
        inventory_multiplier
    )

    simulated_competitor_price = (
        competitor_price *
        competitor_price_multiplier
    )

    base_units = 100

    predicted_units = (
        base_units *
        demand_multiplier
    )

    predicted_revenue = (
        predicted_units *
        current_price
    )

    predicted_profit = (
        predicted_units *
        (current_price * 0.4)
    )

    return {

        "stock_code": stock_code,

        "current_price": current_price,

        "simulated_inventory": simulated_inventory,

        "simulated_competitor_price": simulated_competitor_price,

        "predicted_units": predicted_units,

        "predicted_revenue": predicted_revenue,

        "predicted_profit": predicted_profit,

        "scenario": {

            "demand_multiplier": demand_multiplier,

            "inventory_multiplier": inventory_multiplier,

            "competitor_price_multiplier": competitor_price_multiplier
        }
    }

# Creating endpoint to update actual sales/profit
@app.get("/update_actuals")
def update_actuals(
    stock_code: str,
    actual_units_sold: float,
    actual_profit: float
    ):

    query = """
    UPDATE `pricing-optimization-agent.pricing_agent_dev.prediction_logs`
    SET
        actual_units_sold = @actual_units_sold,
        actual_profit = @actual_profit,
        prediction_error = ABS(predicted_units_sold - @actual_units_sold),
        profit_error = ABS(predicted_profit - @actual_profit)
    WHERE stock_code = @stock_code
    """

    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter(
                "stock_code",
                "STRING",
                stock_code
            ),

            bigquery.ScalarQueryParameter(
                "actual_units_sold",
                "FLOAT64",
                actual_units_sold
            ),

            bigquery.ScalarQueryParameter(
                "actual_profit",
                "FLOAT64",
                actual_profit
            )
        ]
    )

    client.query(query, job_config=job_config)

    return {
        "message": "Actuals updated successfully"
    }


@app.get("/simulate")
def simulate_price(stock_code: str, test_price: float):

    query = """
    SELECT
        *
    FROM ML.PREDICT(
        MODEL `pricing-optimization-agent.pricing_agent_dev.demand_model`,
        (
            SELECT
                StockCode,
                start_week,
                @test_price AS avg_price,
                lag_1_units,
                lag_2_units,
                rolling_4_wk_units,
                rolling_4_wk_price,
                price_change_pct,
                cost,
                (@test_price - cost) AS avg_margins
            FROM `pricing-optimization-agent.pricing_agent_dev.candidate_price_grid`
            WHERE StockCode = @stock_code
            ORDER BY start_week DESC
            LIMIT 1
        )
    )
    """

    job_config = bigquery.QueryJobConfig(
    query_parameters=[
        bigquery.ScalarQueryParameter("stock_code", "STRING", stock_code),
        bigquery.ScalarQueryParameter("test_price", "FLOAT64", test_price)
    ]
    )

    results = client.query(query, job_config=job_config).to_dataframe()

    if results.empty:
        return {"message": "No simulation result found"}

    row = results.iloc[0]

    predicted_units = float(row["predicted_units_sold"])
    unit_cost = float(row["cost"])
    predicted_profit = predicted_units * (test_price - unit_cost)

    return {
        "stock_code": stock_code,
        "test_price": test_price,
        "predicted_units": predicted_units,
        "cost": unit_cost,
        "predicted_profit": predicted_profit
        
    }

@app.get("/simulate_range")
def simulate_range(stock_code: str):

    query = """
    SELECT
        avg_price AS price,
        predicted_units_sold,
        predicted_units_sold * (avg_price - cost) AS profit
    FROM ML.PREDICT(
        MODEL `pricing-optimization-agent.pricing_agent_dev.demand_model`,
        (
            SELECT
                StockCode,
                start_week,
                p AS avg_price,
                lag_1_units,
                lag_2_units,
                rolling_4_wk_units,
                rolling_4_wk_price,
                price_change_pct,
                cost,
                (p - cost) AS avg_margins
            FROM `pricing-optimization-agent.pricing_agent_dev.candidate_price_grid`,
            UNNEST(GENERATE_ARRAY(1, 50, 1)) AS p
            WHERE StockCode = @stock_code
            LIMIT 50
        )
    )
    """

    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("stock_code", "STRING", stock_code)
        ]
    )

    results = client.query(query, job_config=job_config).to_dataframe()

    return results.to_dict(orient="records")


## Checking form alerts
@app.get("/check_alerts")
def check_alerts():

    query = """
    SELECT *
    FROM pricing_agent_dev.error_alert
    WHERE status = 'ALERT'
    """

    result = client.query(query).to_dataframe()

    return result.to_dict(orient="records")

## Automatic retraining decision
@app.get("/monitor_model")
def monitor_model():

    query = """
    SELECT *
    FROM pricing_agent_dev.error_alert
    WHERE status = 'ALERT'
    """

    results = client.query(query).to_dataframe()

    if results.empty:

        return {
            "status": "MODEL_HEALTHY"
        }

    else:

        return {
            "status": "RETRAIN_REQUIRED",
            "affected_skus": results.to_dict(orient="records")
        }
    
# Batch recommendation
@app.get("/batch_recommend")
def batch_recommend():

    # 🔥 get list of SKUs (latest available)
    query = """
    SELECT DISTINCT StockCode
    FROM `pricing-optimization-agent.pricing_agent_dev.price_recommendations_final_with_explainability_feture`
    """

    skus = client.query(query).to_dataframe()["StockCode"].tolist()

    results = []

    for sku in skus:

        try:
            # 🔥 reuse your recommend logic
            res = recommend_price(sku)

            results.append({
                "stock_code": sku,
                "status": "success"
            })

        except Exception as e:
            results.append({
                "stock_code": sku,
                "status": "failed",
                "error": str(e)
            })

    return {
        "processed": len(results),
        "results": results
    }


## Safe entreprise sandbox . Sandbox result table
@app.get("/sandbox_simulation")
def sandbox_simulation(

    stock_code: str,

    historical_period: str = "BlackFriday2024",

    test_price: float = 15.0
):

    base_units = 500

    simulated_units = (
        base_units *
        1.5
    )

    simulated_revenue = (
        simulated_units *
        test_price
    )

    simulated_profit = (
        simulated_units *
        (test_price * 0.4)
    )

    sandbox_rows = [
        {
            "simulation_time": datetime.utcnow().isoformat(),

            "simulation_name": "black_friday_replay",

            "stock_code": stock_code,

            "historical_period": historical_period,

            "simulated_price": test_price,

            "simulated_units": simulated_units,

            "simulated_revenue": simulated_revenue,

            "simulated_profit": simulated_profit
        }
    ]  