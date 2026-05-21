from google.cloud import aiplatform

PROJECT_ID = "pricing-optimization-agent"
REGION = "us-central1"

ENDPOINT_ID = "6488148296517812224"

aiplatform.init(
    project=PROJECT_ID,
    location=REGION
)

endpoint = aiplatform.Endpoint(
    f"projects/{PROJECT_ID}/locations/{REGION}/endpoints/{ENDPOINT_ID}"
)

response = endpoint.predict(
    instances=[
        [10, 100, 90, 110, 9.5]
    ]
)

print(response.predictions)