import streamlit as st
import plotly.express as px
from google.cloud import bigquery
import pandas as pd
import requests

st.set_page_config(
    page_title="AI Pricing Agent Dashboard",
    layout="wide"
)

st.title("AI Pricing Optimization Dashboard")

st.subheader("System Status")

st.success("Dashboard connected successfully")

client = bigquery.Client(
    project="pricing-optimization-agent"
)

query = """
SELECT *
FROM `pricing-optimization-agent.pricing_agent_dev.prediction_logs`
ORDER BY prediction_time DESC
LIMIT 20
"""

df = client.query(query).to_dataframe()

st.subheader("Recent Predictions")

st.dataframe(df)

st.subheader("System KPIs")

total_predictions = len(df)

avg_predicted_profit = (
    df["predicted_profit"].astype(float).mean()
)

avg_actual_profit = (
    df["actual_profit"].astype(float).mean()
)

drift_alerts = (
    df["prediction_error"]
    .notnull()
    .sum()
)

col1, col2, col3, col4 = st.columns(4)

col1.metric(
    "Predictions",
    total_predictions
)

col2.metric(
    "Avg Predicted Profit",
    round(avg_predicted_profit, 2)
)

col3.metric(
    "Avg Actual Profit",
    round(avg_actual_profit, 2)
)

col4.metric(
    "Records With Errors",
    drift_alerts
)


## Active model status
st.subheader("Active Model Status")

model_query = """
SELECT *

FROM `pricing-optimization-agent.pricing_agent_dev.model_registry`

WHERE model_status = 'ACTIVE'

ORDER BY deployment_time DESC

LIMIT 1
"""

model_df = client.query(
    model_query
).to_dataframe()

st.dataframe(model_df)


## displaying retraining history in dashboard
st.subheader("Retraining History")

retraining_query = """
SELECT *

FROM `pricing-optimization-agent.pricing_agent_dev.retraining_logs`

ORDER BY retraining_time DESC

LIMIT 10
"""

retraining_df = client.query(
    retraining_query
).to_dataframe()

st.dataframe(retraining_df)



## Model drift
st.subheader("Model Drift Alerts")

alert_query = """
SELECT *
FROM `pricing-optimization-agent.pricing_agent_dev.error_alert`
"""

alerts_df = client.query(
    alert_query
).to_dataframe()

if alerts_df.empty:

    st.success("No active alerts")

else:

    for _, row in alerts_df.iterrows():

        severity = row["status"]

        message = (
            f"SKU: {row['stock_code']} | "
            f"Severity: {severity}"
        )

        if severity == "CRITICAL":

            st.error(message)

        elif severity == "RETRAIN_REQUIRED":

            st.warning(message)

        elif severity == "WARNING":

            st.info(message)

        else:

            st.success(message)

    st.dataframe(alerts_df)


## A/B testing monitoring
st.subheader("A/B Testing Performance")

ab_query = """
SELECT

    ab_group,

    COUNT(*) AS total_sessions,

    AVG(actual_profit) AS avg_profit,

    AVG(actual_units) AS avg_units,


FROM `pricing-optimization-agent.pricing_agent_dev.pricing_outcomes_log`

WHERE ab_group IS NOT NULL

GROUP BY ab_group
"""

ab_df = client.query(
    ab_query
).to_dataframe()

st.dataframe(ab_df)    


## live visibility into what the AI is recommending

st.subheader("Live Pricing Recommendations")

recommendation_query = """
SELECT

    StockCode,

    recommended_price,

    predicted_profit,

    predicted_units,

    model_version,

    ab_group,

    timestamp

FROM `pricing-optimization-agent.pricing_agent_dev.pricing_outcomes_log`

ORDER BY timestamp DESC

LIMIT 20
"""

recommendation_df = client.query(
    recommendation_query
).to_dataframe()

st.dataframe(recommendation_df)


## Human human approval before deployment/ manual oversight n auditability.Approval control/governance/Human in the loop
st.subheader("Approve Pricing Recommendation")

stock_code_input = st.text_input(
    "Stock Code"
)

recommended_price_input = st.number_input(
    "Recommended Price",
    min_value=0.0
)

approval_status = st.selectbox(
    "Approval Decision",
    ["APPROVED", "REJECTED"]
)

approved_by = st.text_input(
    "Approved By"
)

approval_notes = st.text_area(
    "Notes"
)

if st.button("Submit Approval"):

    approval_query = f"""
    INSERT INTO
    `pricing-optimization-agent.pricing_agent_dev.price_approvals`

    (
        approval_time,
        StockCode,
        recommended_price,
        approval_status,
        approved_by,
        notes
    )

    VALUES

    (
        CURRENT_TIMESTAMP(),
        '{stock_code_input}',
        {recommended_price_input},
        '{approval_status}',
        '{approved_by}',
        '{approval_notes}'
    )
    """

    client.query(approval_query)

    st.success("Approval submitted successfully")

##  Approval history panel
st.subheader("Approval History")

approval_history_query = """
SELECT *

FROM `pricing-optimization-agent.pricing_agent_dev.price_approvals`

ORDER BY approval_time DESC

LIMIT 20
"""

approval_history_df = client.query(
    approval_history_query
).to_dataframe()

st.dataframe(approval_history_df)


## Simulation control- “What happens if we price this product at $12?”
st.subheader("Pricing Simulation")

simulation_stock = st.text_input(
    "Simulation Stock Code"
)

simulation_price = st.number_input(
    "Simulation Price",
    min_value=0.0,
    key="simulation_price"
)

if st.button("Run Simulation"):

    simulation_url = (
        f"http://127.0.0.1:8000/simulate"
        f"?stock_code={simulation_stock}"
        f"&test_price={simulation_price}"
    )

    simulation_response = requests.get(
        simulation_url
    )

    simulation_result = simulation_response.json()

    st.json(simulation_result)


## Profit trends over time
st.subheader("Predicted Profit Trend")

profit_query = """
SELECT

    timestamp,

    predicted_profit

FROM `pricing-optimization-agent.pricing_agent_dev.pricing_outcomes_log`

WHERE predicted_profit IS NOT NULL

ORDER BY timestamp
"""

profit_df = client.query(
    profit_query
).to_dataframe()

fig = px.line(
    profit_df,
    x="timestamp",
    y="predicted_profit",
    title="Predicted Profit Over Time"
)

st.plotly_chart(
    fig,
    use_container_width=True
)

## Ai chat Assistnat 
st.subheader("AI Pricing Assistant")

chat_stock_code = st.text_input(
    "Stock Code for AI Assistant"
)

chat_question = st.text_area(
    "Ask the AI Assistant"
)

if st.button("Ask AI Assistant"):

    chat_url = (
        f"http://127.0.0.1:8000/chat_explain"
        f"?stock_code={chat_stock_code}"
        f"&question={chat_question}"
    )

    chat_response = requests.get(
        chat_url
    )

    result = chat_response.json()

    st.markdown("### AI Response")

    if "response" in result:

        st.write(result["response"])

    else:

        st.error(result)

## DAta quality
st.subheader("Data Quality Monitoring")

dq_query = """
SELECT *
FROM `pricing-optimization-agent.pricing_agent_dev.data_quality_alerts`
ORDER BY check_time DESC
LIMIT 10
"""

dq_df = client.query(
    dq_query
).to_dataframe()

if dq_df.empty:

    st.success("No data quality issues detected")

else:

    for _, row in dq_df.iterrows():

        status = row["alert_status"]

        if status == "HEALTHY":

            st.success(status)

        else:

            st.error(status)

    st.dataframe(dq_df)        


## Stale Date section
st.subheader("Stale Data Monitoring")

stale_query = """
SELECT *
FROM `pricing-optimization-agent.pricing_agent_dev.stale_data_monitor`
ORDER BY check_time DESC
LIMIT 5
"""

stale_df = client.query(
    stale_query
).to_dataframe()

if stale_df.empty:

    st.info("No stale data records found")

else:

    for _, row in stale_df.iterrows():

        status = row["data_status"]

        if status == "STALE_DATA":

            st.error(
                f"Data stale for {row['days_since_latest_data']} days"
            )

        else:

            st.success("Feature data is fresh")

    st.dataframe(stale_df)


## Pipeline health section
st.subheader("Pipeline Health Monitoring")

pipeline_query = """
SELECT *
FROM `pricing-optimization-agent.pricing_agent_dev.pipeline_health_monitor`
ORDER BY check_time DESC
LIMIT 5
"""

pipeline_df = client.query(
    pipeline_query
).to_dataframe()

if pipeline_df.empty:

    st.info("No pipeline health data found")

else:

    for _, row in pipeline_df.iterrows():

        status = row["pipeline_status"]

        if status == "PIPELINE_FAILURE":

            st.error(status)

        elif status == "LOW_DATA_WARNING":

            st.warning(status)

        else:

            st.success(status)

    st.dataframe(pipeline_df)    

## Audit trail for compliance and traceability
st.subheader("Audit Trail")

audit_query = """
SELECT *
FROM `pricing-optimization-agent.pricing_agent_dev.audit_trail`
ORDER BY audit_time DESC
LIMIT 20
"""

audit_df = client.query(
    audit_query
).to_dataframe()

if audit_df.empty:

    st.info("No audit records found")

else:

    st.dataframe(audit_df)
