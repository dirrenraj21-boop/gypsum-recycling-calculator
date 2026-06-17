import streamlit as st
import pandas as pd
import plotly.express as px
import folium
from streamlit_folium import st_folium
import requests
from itertools import combinations
from ortools.constraint_solver import routing_enums_pb2
from ortools.constraint_solver import pywrapcp

st.set_page_config(page_title="Gypsum Recycling Dashboard", layout="wide")

st.title("♻️ Gypsum Recycling Dashboard")
st.caption("Profit-based route optimisation using free OSRM + OR-Tools")

with st.sidebar:
    st.header("Input Parameters")
    processing_cost_perkg = st.number_input("Processing cost (RM/kg)", min_value=0.0, value=10.0)
    pot_weight = st.number_input("Pot weight (g)", min_value=1.0, value=70.0)
    selling_price = st.number_input("Selling price per pot (RM)", min_value=0.0, value=5.0)

    st.header("Transport Parameters")
    fuel_price = st.number_input("Fuel Price (RM/L)", min_value=0.0, value=2.05, step=0.01)
    fuel_efficiency = st.number_input("Vehicle Fuel Efficiency (km/L)", min_value=1.0, value=12.0, step=0.5)

    st.header("Carbon Emission Parameters")
    virgin_carbon_factor = st.number_input("Virgin Gypsum Carbon Factor (kg CO₂e/kg)", min_value=0.0, value=0.30, step=0.01)
    reduction_percent = st.number_input("CO₂ Reduction Compared With Virgin Gypsum (%)", min_value=0, max_value=100, value=45) / 100

yield_rate = 0.8791


def get_osrm_table(points):
    coords = ";".join(f"{p['longitude']},{p['latitude']}" for p in points)

    url = (
        f"https://router.project-osrm.org/table/v1/driving/{coords}"
        "?annotations=distance,duration"
    )

    response = requests.get(url, timeout=20)
    data = response.json()

    if response.status_code == 200 and data.get("code") == "Ok":
        return data["distances"], data["durations"]

    return None, None


def solve_tsp_for_subset(distance_matrix, subset_indices):
    submatrix = [
        [distance_matrix[i][j] for j in subset_indices]
        for i in subset_indices
    ]

    manager = pywrapcp.RoutingIndexManager(len(submatrix), 1, 0)
    routing = pywrapcp.RoutingModel(manager)

    def distance_callback(from_index, to_index):
        from_node = manager.IndexToNode(from_index)
        to_node = manager.IndexToNode(to_index)
        return int(submatrix[from_node][to_node])

    callback_index = routing.RegisterTransitCallback(distance_callback)
    routing.SetArcCostEvaluatorOfAllVehicles(callback_index)

    search_parameters = pywrapcp.DefaultRoutingSearchParameters()
    search_parameters.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    search_parameters.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    search_parameters.time_limit.seconds = 3

    solution = routing.SolveWithParameters(search_parameters)

    if not solution:
        return [], 0

    index = routing.Start(0)
    route_local = []
    total_distance = 0

    while not routing.IsEnd(index):
        route_local.append(manager.IndexToNode(index))
        previous_index = index
        index = solution.Value(routing.NextVar(index))
        total_distance += routing.GetArcCostForVehicle(previous_index, index, 0)

    route_local.append(0)

    route_global = [subset_indices[i] for i in route_local]

    return route_global, total_distance


st.subheader("🏥 Clinic Collection Planner")

clinic_data = pd.DataFrame({
    "Include": [True, True, True, False, False, False, False, False, False, False],
    "Clinic": [
        "Klinik Pergigian Indera Mahkota",
        "Klinik Pergigian Bandar Kuantan",
        "UIA School of Dentistry",
        "Klinik Pergigian Beserah",
        "Klinik Pergigian Jaya Gading",
        "Klinik Pergigian Gambut",
        "Klinik Pergigian Kurnia",
        "Klinik Pergigian Balok",
        "Klinik Pergigian Gambang",
        "Klinik Pergigian Pekan"
    ],
    "latitude": [3.8160, 3.8077, 3.8155, 3.8147, 3.7865, 3.8335, 3.8228, 3.9490, 3.7240, 3.4890],
    "longitude": [103.2960, 103.3260, 103.3000, 103.3640, 103.2540, 103.3170, 103.3310, 103.3730, 103.0830, 103.3890],
    "Gypsum Available (kg)": [5.0, 4.0, 6.0, 3.0, 2.0, 4.0, 3.0, 5.0, 4.0, 5.0]
})

clinic_data = st.data_editor(
    clinic_data,
    column_config={
        "Include": st.column_config.CheckboxColumn("Consider for collection"),
        "Gypsum Available (kg)": st.column_config.NumberColumn(
            "Gypsum Available (kg)",
            min_value=0.0,
            step=0.5
        )
    },
    hide_index=True,
    use_container_width=True
)

candidate_clinics = clinic_data[clinic_data["Include"] == True].copy()

start_point = {
    "Clinic": "Regent International School",
    "latitude": 3.8246,
    "longitude": 103.3280,
    "Gypsum Available (kg)": 0.0
}

route_coordinates = []
route_order = []
distance_km = 0
duration_min = 0
fuel_used = 0
transport_cost = 0

best_profit = -999999
best_route_indices = []
best_selected_indices = []
best_distance_m = 0

points = [start_point] + candidate_clinics.to_dict("records")

if len(candidate_clinics) > 0:
    distance_matrix, duration_matrix = get_osrm_table(points)

    if distance_matrix:
        clinic_indices = list(range(1, len(points)))

        for r in range(1, len(clinic_indices) + 1):
            for subset in combinations(clinic_indices, r):
                subset_indices = [0] + list(subset)

                route_indices, total_meters = solve_tsp_for_subset(
                    distance_matrix,
                    subset_indices
                )

                if not route_indices:
                    continue

                selected_rows = candidate_clinics.iloc[
                    [i - 1 for i in subset]
                ]

                gypsum_subset = selected_rows["Gypsum Available (kg)"].sum()
                recovered_subset = gypsum_subset * yield_rate
                pots_subset = (recovered_subset * 1000) / pot_weight if pot_weight > 0 else 0

                revenue_subset = pots_subset * selling_price
                processing_subset = gypsum_subset * processing_cost_perkg

                distance_subset_km = total_meters / 1000
                fuel_subset = distance_subset_km / fuel_efficiency if fuel_efficiency > 0 else 0
                transport_subset = fuel_subset * fuel_price

                profit_subset = revenue_subset - processing_subset - transport_subset

                if profit_subset > best_profit:
                    best_profit = profit_subset
                    best_route_indices = route_indices
                    best_selected_indices = list(subset)
                    best_distance_m = total_meters

        route_order = [points[i]["Clinic"] for i in best_route_indices]

        distance_km = best_distance_m / 1000
        fuel_used = distance_km / fuel_efficiency if fuel_efficiency > 0 else 0
        transport_cost = fuel_used * fuel_price

        duration_seconds = 0

        for i in range(len(best_route_indices) - 1):
            origin_index = best_route_indices[i]
            destination_index = best_route_indices[i + 1]

            duration_seconds += duration_matrix[origin_index][destination_index]

            origin = points[origin_index]
            destination = points[destination_index]

            coords = (
                f"{origin['longitude']},{origin['latitude']};"
                f"{destination['longitude']},{destination['latitude']}"
            )

            route_url = (
                f"https://router.project-osrm.org/route/v1/driving/{coords}"
                "?overview=full&geometries=geojson"
            )

            try:
                route_response = requests.get(route_url, timeout=20)
                route_data = route_response.json()

                if route_response.status_code == 200 and route_data.get("code") == "Ok":
                    segment_coords = [
                        [lat, lon]
                        for lon, lat in route_data["routes"][0]["geometry"]["coordinates"]
                    ]
                    route_coordinates.extend(segment_coords)

            except:
                pass

        duration_min = duration_seconds / 60

    else:
        st.error("OSRM could not calculate the distance matrix. Try again later.")

if best_selected_indices:
    selected_route_df = candidate_clinics.iloc[
        [i - 1 for i in best_selected_indices]
    ].copy()
else:
    selected_route_df = pd.DataFrame(columns=candidate_clinics.columns)

gypsum_kg = selected_route_df["Gypsum Available (kg)"].sum()
recovered_gypsum = gypsum_kg * yield_rate
pots = (recovered_gypsum * 1000) / pot_weight if pot_weight > 0 else 0
processing_cost = gypsum_kg * processing_cost_perkg
revenue = pots * selling_price
carbon_saved = recovered_gypsum * virgin_carbon_factor * reduction_percent
profit = revenue - processing_cost - transport_cost

col1, col2, col3, col4, col5, col6 = st.columns(6)

col1.metric("♻️ Gypsum Collected", f"{gypsum_kg:.2f} kg")
col2.metric("♻️ Recovered Powder", f"{recovered_gypsum:.2f} kg")
col3.metric("🏺 Pots Produced", f"{pots:.0f}")
col4.metric("💰 Revenue", f"RM {revenue:.2f}")
col5.metric("📈 Profit", f"RM {profit:.2f}")
col6.metric("🌱 CO₂ Reduction", f"{carbon_saved:.2f} kg CO₂e")

st.caption(
    "The model tests possible clinic combinations, selects the most profitable collection set, then optimises the shortest route using OSRM + OR-Tools."
)

st.divider()

colA, colB, colC, colD = st.columns(4)

colA.metric("🚚 Optimised Distance", f"{distance_km:.2f} km")
colB.metric("⛽ Fuel Used", f"{fuel_used:.2f} L")
colC.metric("⏱️ Driving Time", f"{duration_min:.0f} min")
colD.metric("💸 Transport Cost", f"RM {transport_cost:.2f}")

st.divider()

if profit > 0:
    st.success("✅ Recommended route is financially viable.")
else:
    st.error("❌ No financially viable collection route found based on current assumptions.")

if route_order:
    st.subheader("🚚 Recommended Optimal Route")
    for i, stop in enumerate(route_order, start=1):
        st.write(f"{i}. {stop}")

if len(selected_route_df) > 0:
    st.subheader("✅ Clinics Recommended for Collection")
    st.dataframe(
        selected_route_df[["Clinic", "Gypsum Available (kg)"]],
        hide_index=True,
        use_container_width=True
    )

skipped_df = candidate_clinics[
    ~candidate_clinics["Clinic"].isin(selected_route_df["Clinic"])
]

if len(skipped_df) > 0:
    st.subheader("⏭️ Clinics Skipped by Optimiser")
    st.dataframe(
        skipped_df[["Clinic", "Gypsum Available (kg)"]],
        hide_index=True,
        use_container_width=True
    )

st.divider()

st.subheader("📊 Cost Breakdown")

chart_data = pd.DataFrame({
    "Category": ["Revenue", "Processing Cost", "Transport Cost", "Profit"],
    "RM": [revenue, processing_cost, transport_cost, profit]
})

fig = px.bar(
    chart_data,
    x="Category",
    y="RM",
    text="RM",
    title="Cost and Revenue Breakdown"
)

fig.update_traces(texttemplate="RM %{y:.2f}", textposition="outside")
fig.update_layout(xaxis_title="", yaxis_title="RM", showlegend=False)

st.plotly_chart(fig, use_container_width=True)

st.divider()

st.subheader("🗺️ Optimised Collection Map")

m = folium.Map(location=[3.812, 103.307], zoom_start=11, tiles="CartoDB positron")

folium.Marker(
    location=[start_point["latitude"], start_point["longitude"]],
    popup="<b>Regent International School</b><br>Start/End Point",
    tooltip="Regent International School",
    icon=folium.Icon(color="blue", icon="home", prefix="fa")
).add_to(m)

for _, row in selected_route_df.iterrows():
    folium.Marker(
        location=[row["latitude"], row["longitude"]],
        popup=f"""
        <b>{row['Clinic']}</b><br>
        Gypsum available: {row['Gypsum Available (kg)']} kg
        """,
        tooltip=row["Clinic"],
        icon=folium.Icon(color="green", icon="leaf", prefix="fa")
    ).add_to(m)

if route_coordinates:
    folium.PolyLine(route_coordinates, color="blue", weight=5, opacity=0.8).add_to(m)

st_folium(m, width=1000, height=500)