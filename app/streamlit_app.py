import requests
import streamlit as st


API_URL = "http://127.0.0.1:8000/recommendations"


st.set_page_config(
    page_title="YUMMY Recommendations",
    page_icon="🍽️",
    layout="wide",
)

st.title("🍽️ YUMMY — Recipe Recommendations")

st.write(
    "Recommandations de recettes basées sur un premier score YUMMY."
)

limit = st.slider(
    "Nombre de recommandations",
    min_value=5,
    max_value=30,
    value=10,
    step=5,
)

if st.button("Obtenir les recommandations"):
    response = requests.get(
        API_URL,
        params={"limit": limit},
        timeout=10,
    )

    if response.status_code == 200:
        recipes = response.json()

        for recipe in recipes:
            st.subheader(recipe["name"])
            st.write(f"**Score YUMMY :** {recipe['yummy_score']}/100")
            st.write(f"**Note :** {recipe['aggregatedrating']}/5")
            st.write(f"**Temps total :** {recipe['totaltime']} minutes")
            st.divider()
    else:
        st.error("Erreur lors de l'appel API.")