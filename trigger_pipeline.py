from google.cloud import aiplatform
import requests

PROJECT_ID = "pricing-optimization-agent"
REGION = "us-central1"

aiplatform.init(
    project=PROJECT_ID,
    location=REGION
)

monitor_response = requests.get(
    "YOUR_FASTAPI_URL/monitor_model"
)

monitor_data = monitor_response.json()

if monitor_data["status"] == "MODEL_HEALTHY":

    return "No retraining needed"


job = aiplatform.PipelineJob(
    display_name="scheduled-pricing-pipeline",
    template_path="pipeline.json",
    pipeline_root="gs://pricing-models-bucket/pipeline-root"
)

job.run()

print("Pipeline triggered successfully")