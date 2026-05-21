import streamlit as st
import requests

import os

port = int(os.environ.get("PORT", 8501))
st.set_page_config(layout="wide")

st.title("Pricing Optimization Agent")

# input
sku = st.text_input("Enter Stock Code (SKU)", "85123A")

# button
if st.button("Get Recommendation"):

    url = f"https://pricing-agent-300192014618.us-central1.run.app/recommend?stock_code={sku}"

    response = requests.get(url)
    st.write(response.status_code)
    st.write(response.text)

    if response.status_code == 200:
        data = response.json()

        st.subheader("Recommendation")

        st.write(f"**Recommended Price:** {data.get('recommended_price')}")
        st.write(f"**Profit:** {data.get('profit')}")
        st.write(f"**Confidence:** {data.get('confidence_score')}")
        st.write(f"**Risk:** {data.get('risk_score')}")
        st.write(f"**Price Change %:** {data.get('price_change_pct')}")

        st.subheader("Explanation")
        st.write(data.get("reason"))

    else:
        st.error("Failed to get recommendation")