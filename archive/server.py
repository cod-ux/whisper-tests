from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import asyncio
import os
from dotenv import load_dotenv
import logging
from fixa import Test, Agent, Scenario, Evaluation, TestRunner
from fixa.evaluators import LocalEvaluator
import ngrok
import time

# Set up logging
logging.basicConfig(
    level=logging.DEBUG, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv(override=True)

app = FastAPI()
TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)


# Define Pydantic model for request validation
class EvaluationModel(BaseModel):
    eval_name: str
    eval_success_criteria: str


class TestModel(BaseModel):
    agent_name: str
    agent_description: str
    scenario_name: str
    scenario_description: str
    evaluations: list[EvaluationModel]


class TestRequest(BaseModel):
    tests: list[TestModel]
    agent_type: str
    phone_number: str | None = None


@app.post("/runTests")
async def run_tests(request_data: TestRequest):
    logger.info("Request received at /runTests")

    # Validate data
    if not request_data.tests:
        return {"error": "No tests provided"}

    agent_type = request_data.agent_type
    phone_number = request_data.phone_number

    if agent_type == "inbound" and not phone_number:
        return {"error": "Phone number is required for inbound agent"}

    # Setup ngrok
    port = 8765

    logger.info(f"Setting up ngrok on port {port}")
    listener = await ngrok.forward(port, authtoken=os.getenv("NGROK_AUTH_TOKEN"))

    # Load tests
    loaded_tests = []
    for test in request_data.tests:
        agent = Agent(name=test.agent_name, prompt=test.agent_description)
        scenario = Scenario(
            name=test.scenario_name,
            prompt=test.scenario_description,
            evaluations=[
                Evaluation(name=e.eval_name, prompt=e.eval_success_criteria)
                for e in test.evaluations
            ],
        )
        loaded_tests.append(Test(agent=agent, scenario=scenario))

    # Create test runner
    test_runner = TestRunner(
        port=port,
        ngrok_url=listener.url(),
        twilio_phone_number=TWILIO_PHONE_NUMBER,
        evaluator=LocalEvaluator(model="gpt-4o"),
    )

    for test in loaded_tests:
        test_runner.add_test(test)

    logger.info("Running tests asynchronously...")

    test_results = None
    try:
        if agent_type == "inbound":
            test_results = await test_runner.run_tests(
                phone_number=phone_number, type=TestRunner.OUTBOUND
            )
        else:
            test_results = ""

    except asyncio.exceptions.CancelledError as e:
        logger.error(f"Task was cancelled: {e}")

    except Exception as e:
        logger.error(
            f"Error running tests: {e}", exc_info=True
        )  # Add exc_info=True to get the full traceback

    if test_results:
        print("Here are the test results: \n", test_results)
        await asyncio.sleep(1)
        return test_results
    else:
        print("Test results were empty")
        return {"error": "test results turned out to be empty"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=5001)
