from kfp import dsl
from kfp.dsl import component
from google.cloud import bigquery
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
import pickle


#  Load dataset
from kfp.dsl import component, Output, Dataset

@component(
    packages_to_install=[
        "google-cloud-bigquery"
    ]
)
def load_data(dataset: Output[Dataset]):

    from google.cloud import bigquery
    import csv

    client = bigquery.Client(project="pricing-optimization-agent")

    query = """
    SELECT
        avg_price,
        lag_1_units,
        lag_2_units,
        rolling_4_wk_units,
        rolling_4_wk_price,
        units_sold
    FROM `pricing-optimization-agent.pricing_agent_dev.model_dataset`
    """

    results = client.query(query).result()

    with open(dataset.path, "w", newline="") as csvfile:

        writer = None

        for row in results:

            if writer is None:
                writer = csv.DictWriter(csvfile, fieldnames=row.keys())
                writer.writeheader()

            writer.writerow(dict(row))

# train model

from kfp.dsl import Output, Model, Input

@component(
    packages_to_install=[
        "pandas==2.2.2",
        "numpy==1.26.4",
        "scikit-learn==1.4.2"
            ]
        )


def train_model(
    dataset: Input[Dataset],
    model: Output[Model]
    ):

    import pandas as pd
    import pickle
    from sklearn.ensemble import RandomForestRegressor

    df = pd.read_csv(dataset.path)

    df.columns = df.columns.str.lower()

    print("COLUMNS:")
    print(df.columns.tolist())

    
    features = [
        "avg_price",
        "lag_1_units",
        "lag_2_units",
        "rolling_4_wk_units",
        "rolling_4_wk_price"
    ]

    target = "units_sold"

    # keep only required columns
    df = df[features + [target]].dropna()
    df = df.astype(float)

    print(df.head())
    print(df.columns.tolist())

    X = df[features]
    y = df[target]

    rf_model = RandomForestRegressor(
        n_estimators=100,
        random_state=42
    )

    rf_model.fit(X, y)

    with open(model.path, "wb") as f:
     pickle.dump(rf_model, f)



# Component: Evaluate model
from kfp.dsl import Input, Dataset

@component(
    packages_to_install=[
        "pandas==2.2.2",
        "numpy==1.26.4",
        "scikit-learn==1.4.2"
            ]
        )
def evaluate_model(
    dataset: Input[Dataset],
    model: Input[Model]
    ) -> float:

    import pandas as pd
    import pickle
    from sklearn.metrics import mean_absolute_error

    df = pd.read_csv(dataset.path)

    df.columns = df.columns.str.lower()

    features = [
        "avg_price",
        "lag_1_units",
        "lag_2_units",
        "rolling_4_wk_units",
        "rolling_4_wk_price"
    ]

    target = "units_sold"

    df = df[features + [target]].dropna()
    df = df.astype(float)

    X = df[features]
    y = df[target]

    with open(model.path, "rb") as f:
        model = pickle.load(f)

    preds = model.predict(X)

    mae = mean_absolute_error(y, preds)

    return mae


# Component: Decide
@component
def decide(mae: float) -> str:
    threshold = 50

    if mae < threshold:
        return "DEPLOY"
    else:
        return "KEEP_OLD"


# Component: Deploy
from kfp.dsl import Input, Model

@component(
    packages_to_install=[
        "google-cloud-storage",
        "google-cloud-aiplatform"
    ]
)
def deploy_model(
    model: Input[Model],
    decision: str
) -> str:

    from google.cloud import storage, aiplatform
    from datetime import datetime

    if decision != "DEPLOY":
        return "Model not deployed"

    PROJECT_ID = "pricing-optimization-agent"
    REGION = "us-central1"
    BUCKET = "pricing-models-bucket"

    aiplatform.init(
        project=PROJECT_ID,
        location=REGION
    )

    version = f"model_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"

    # upload model artifact to GCS
    storage_client = storage.Client()

    bucket = storage_client.bucket(BUCKET)

    blob_path = f"models/{version}/model.pkl"

    blob = bucket.blob(blob_path)

    blob.upload_from_filename(model.path)

    gcs_uri = f"gs://{BUCKET}/models/{version}"

    # register model in Vertex AI
    vertex_model = aiplatform.Model.upload(
        display_name=version,
        artifact_uri=gcs_uri,
        serving_container_image_uri="us-docker.pkg.dev/vertex-ai/prediction/sklearn-cpu.1-5:latest"
    )

    # create endpoint
    endpoint = aiplatform.Endpoint.create(
        display_name="pricing-endpoint"
    )

    # deploy model to endpoint
    vertex_model.deploy(
        endpoint=endpoint,
        machine_type="n1-standard-2"
    )

    return f"Model deployed to endpoint: {endpoint.resource_name}"

    

# FINAL PIPELINE (ONLY ONE)
@dsl.pipeline(name="pricing-retraining-pipeline")
def pipeline():

    data_task = load_data()

    train_task = train_model(
    dataset=data_task.outputs["dataset"])

    eval_task = evaluate_model(
    dataset=data_task.outputs["dataset"],
    model=train_task.outputs["model"]
    )

    decision_task = decide(mae=eval_task.output)

    deploy_task = deploy_model(
        model=train_task.outputs["model"],
        decision=decision_task.output
    )


# Compile
if __name__ == "__main__":
    from kfp import compiler

    compiler.Compiler().compile(
        pipeline_func=pipeline,
        package_path="pipeline.json"
    )