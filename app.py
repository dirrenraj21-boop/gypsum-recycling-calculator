import streamlit as st
import streamlit as st

PASSWORD = "ezgigi2026"

password = st.text_input("Enter password", type="password")

if password != PASSWORD:
    st.warning("Please enter the correct password to access EzGiGi Recycle.")
    st.stop()
import pandas as pd

st.set_page_config(page_title="Gypsum Recycling Calculator", layout="wide")

st.title("♻️ Gypsum Recycling Calculator")
st.caption("Estimate processing cost, pot production, revenue and profit")

with st.sidebar:
    st.header("Enter values")

    gypsum_kg = st.number_input("Gypsum collected (kg)", value=10.0)
    processing_cost_per_kg = st.number_input("Processing cost (RM/kg)", value=10.0)
    pot_weight_g = st.number_input("Gypsum per pot (g)", value=70.0)
    selling_price = st.number_input("Selling price per pot (RM)", value=3.00)
    transport_cost = st.number_input("Transport cost (RM)", value=0.0)

pots = (gypsum_kg * 1000) / pot_weight_g
processing_cost = gypsum_kg * processing_cost_per_kg
revenue = pots * selling_price
profit = revenue - processing_cost - transport_cost
cost_per_pot = processing_cost_per_kg * pot_weight_g / 1000

col1, col2, col3, col4 = st.columns(4)

col1.metric("🏺 Pots Produced", f"{pots:.0f}")
col2.metric("💰 Revenue", f"RM {revenue:.2f}")
col3.metric("⚙️ Processing Cost", f"RM {processing_cost:.2f}")
col4.metric("📈 Profit", f"RM {profit:.2f}")

if profit > 0:
    st.success("✅ This is financially viable")
else:
    st.error("❌ This is not financially viable")

st.subheader("Assumptions")
st.write(f"""
- Processing cost: RM {processing_cost_per_kg:.2f}/kg
- Gypsum per pot: {pot_weight_g:.0f} g
- Cost per pot: RM {cost_per_pot:.2f}
- Selling price: RM {selling_price:.2f}/pot
""")

st.subheader("Cost Breakdown")

data = pd.DataFrame({
    "Category": ["Revenue", "Processing Cost", "Transport Cost", "Profit"],
    "RM": [revenue, processing_cost, transport_cost, profit]
})

st.bar_chart(data.set_index("Category"))