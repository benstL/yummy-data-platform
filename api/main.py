from pathlib import Path

import pandas as pd
from fastapi import FastAPI


app = FastAPI()


GOLD_FILE = Path(
    "data/gold/gold_yummy_recommendations.parquet"
)


@app.get("/")
def root():
    return {
        "message": "YUMMY API is running"
    }


@app.get("/recommendations")
def get_recommendations(limit: int = 10):

    df = pd.read_parquet(GOLD_FILE)

    df = df.sort_values(
        by="yummy_score",
        ascending=False
    )

    recommendations = df.head(limit)

    return recommendations[
        [
            "recipeid",
            "name",
            "yummy_score",
            "aggregatedrating",
            "totaltime",
        ]
    ].to_dict(orient="records")