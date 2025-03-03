import subprocess
import json
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict, Any, Optional

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler("server.log")],
)
logger = logging.getLogger(__name__)


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


class EvaluationResult(BaseModel):
    name: str
    passed: bool
    reason: str


class EvaluationResults(BaseModel):
    evaluation_results: list[EvaluationResult]
    extra_data: Dict[str, Any] | None = None


class Agent(BaseModel):
    name: str
    prompt: str
    voice_id: str


class Scenario(BaseModel):
    name: str
    prompt: str
    evaluations: List[Dict[str, str]]


class Test(BaseModel):
    agent: Agent
    scenario: Scenario


class TestResult(BaseModel):
    test: Test
    evaluation_results: Optional[EvaluationResults] = None
    transcript: List[Dict[str, str]]
    stereo_recording_url: Optional[str] = None
    error: Optional[str] = None


class TestResultsResponse(BaseModel):
    result: List[TestResult]
    error: Optional[str] = None


"""
test_request_data = {
    "tests": [
        {
            "agent_name": "Sarah",
            "agent_description": "Act as the world's best phone rep. You are Jordan, an associate at Dar Global, calling prospects interested in Dar Global's real estate projects. You speak in a natural, conversational manner and avoid numbered lists. Your goal is to answer questions, understand the prospect's needs, and secure a meeting with an expert.",
            "scenario_name": "Recognizing 2 BHK Terminology",
            "scenario_description": "You are calling a prospect who asks if there are any 2 BHK apartments available. They will use the term '2 BHK' naturally in conversation while inquiring about a property in Dubai.",
            "evaluations": [
                {
                    "eval_name": "Correct Recognition of 2 BHK",
                    "eval_success_criteria": "The agent correctly understands '2 BHK' as a '2 Bedroom, Hall, Kitchen' apartment and provides relevant property options.",
                },
                {
                    "eval_name": "Appropriate Response with Property Details",
                    "eval_success_criteria": "The agent provides details of available 2 BHK properties, including price, location, and amenities.",
                },
                {
                    "eval_name": "No Deflection to Irrelevant Properties",
                    "eval_success_criteria": "The agent does not shift focus to other property types unless requested by the prospect.",
                },
            ],
        },
        {
            "agent_name": "Sarah",
            "agent_description": "Act as the world's best phone rep. You are Jordan, an associate at Dar Global, calling prospects interested in Dar Global's real estate projects. You speak in a natural, conversational manner and avoid numbered lists. Your goal is to answer questions, understand the prospect's needs, and secure a meeting with an expert.",
            "scenario_name": "Recognizing 2 BHK Terminology",
            "scenario_description": "You are calling a prospect who asks if there are any 2 BHK apartments available. They will use the term '2 BHK' naturally in conversation while inquiring about a property in Dubai.",
            "evaluations": [
                {
                    "eval_name": "Correct Recognition of 2 BHK",
                    "eval_success_criteria": "The agent correctly understands '2 BHK' as a '2 Bedroom, Hall, Kitchen' apartment and provides relevant property options.",
                },
                {
                    "eval_name": "Appropriate Response with Property Details",
                    "eval_success_criteria": "The agent provides details of available 2 BHK properties, including price, location, and amenities.",
                },
                {
                    "eval_name": "No Deflection to Irrelevant Properties",
                    "eval_success_criteria": "The agent does not shift focus to other property types unless requested by the prospect.",
                },
            ],
        },
    ],
    "agent_type": "inbound",
    "phone_number": "+447436962389",
}"""


app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)


async def run_inbound_subprocess(request_data: TestRequest) -> TestResultsResponse:
    try:
        logger.info(f"Starting subprocess with request data: {request_data}")

        result = subprocess.run(
            ["python", "test_inbound.py"],
            input=json.dumps(request_data.model_dump()),
            text=True,
            encoding="utf-8",
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )

        logger.debug(f"Subprocess output: {result.stdout}")
        logger.debug(f"Return code: {result.returncode}")

        if result.returncode != 0:
            logger.error(f"Subprocess failed with return code {result.returncode}")
            return {"error": f"Subprocess error: {result.stdout}"}

        try:
            start_string = '{"output": '
            json_start = result.stdout.find(start_string)

            if json_start == -1:
                logger.error("JSON start marker not found in subprocess output")
                return {"error": "JSON start not found in subprocess output"}

            json_output = result.stdout[json_start:]
            logger.debug(f"Parsed JSON output: {json_output}")

            output_data = json.loads(json_output)
            return output_data

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON from subprocess output: {e}")
            logger.debug(f"Raw subprocess output: {result.stdout}")
            return {"error": f"JSON parse error: {str(e)}"}

    except Exception as e:
        logger.error(f"Unexpected error in run_inbound_subprocess: {str(e)}", exc_info=True)
        return {"error": str(e)}

async def run_outbound_subprocess(request_data: TestRequest) -> TestResultsResponse:
    try:
        logger.info(f"Starting subprocess with request data: {request_data}")

        result = subprocess.run(
            ["python", "test_outbound.py"],
            input=json.dumps(request_data.model_dump()),
            text=True,
            encoding="utf-8",
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )

        logger.debug(f"Subprocess output: {result.stdout}")
        logger.debug(f"Return code: {result.returncode}")

        try:
            start_string = '{"output": '
            json_start = result.stdout.find(start_string)

            if json_start == -1:
                logger.error("JSON start marker not found in subprocess output")
                return {"error": "JSON start not found in subprocess output"}

            json_output = result.stdout[json_start:]
            logger.debug(f"Parsed JSON output: {json_output}")

            output_data = json.loads(json_output)
            return output_data

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON from subprocess output: {e}")
            logger.debug(f"Raw subprocess output: {result.stdout}")
            return {"error": f"JSON parse error: {str(e)}"}

        if result.returncode != 0:
            logger.error(f"Subprocess failed with return code {result.returncode}")
            return {"error": f"Subprocess error: {result.stdout}"}

        

    except Exception as e:
        logger.error(f"Unexpected error in run_inbound_subprocess: {str(e)}", exc_info=True)
        return {"error": str(e)}

@app.post("/runTests", response_model=TestResultsResponse)
async def run_tests(request_data: TestRequest):
    logger.info("Received /runTests request")
    logger.debug(f"Request data: {request_data}")

    if not request_data.tests:
        logger.error("No tests provided in request")
        return TestResultsResponse(result=[], error="No tests provided")

    if not request_data.agent_type:
        logger.error("Agent type not provided in request")
        return TestResultsResponse(result=[], error="Agent type is required")

    if not request_data.phone_number:
        logger.error("Phone number not provided for voice agent")
        return TestResultsResponse(
            result=[], error="Phone number is required for voice agent"
        )

    if request_data.agent_type == "inbound":
        try:
            result = await run_inbound_subprocess(request_data)
            logger.debug(f"Subprocess result: {result}")

            # Check if result is an error response
            if isinstance(result, dict) and "error" in result:
                logger.error(f"Error from subprocess: {result['error']}")
                return TestResultsResponse(result=[], error=result["error"])

            # Check if result has output
            if isinstance(result, dict) and "output" in result:
                logger.info("Successfully processed test request")
                return TestResultsResponse(result=result["output"], error=None)

            # Fallback error if response format is unexpected
            logger.error(f"Unexpected response format from inbound subprocess: {result}")
            return TestResultsResponse(
                result=[], error="Unexpected response format from inbound subprocess"
            )

        except Exception as e:
            logger.error(f"Exception in run_tests: {str(e)}", exc_info=True)
            return TestResultsResponse(result=[], error=str(e))

    if request_data.agent_type == "outbound":
        try:
            result = await run_outbound_subprocess(request_data)
            logger.debug(f"Subprocess result: {result}")

            if isinstance(result, dict) and "error" in result:
                logger.error(f"Error from subprocess: {result}")
                return TestResultsResponse(result=[], error=result["error"])

            # Check if result has output
            if isinstance(result, dict) and "output" in result:
                logger.info("Successfully processed test request")
                return TestResultsResponse(result=result["output"], error=None)

            logger.error(f"Unexpected response format from outbound subprocess: {result}")
            return TestResultsResponse(
                result=[], error="Unexpected response format from outbound subprocess"
            )

        except Exception as e:
            logger.error(f"Exception in run_tests: {str(e)}", exc_info=True)
            return TestResultsResponse(result=[], error=str(e))


if __name__ == "__main__":
    import uvicorn

    logger.info("Starting server on port 5001")
    uvicorn.run(app, host="0.0.0.0", port=5001)

# run_result = run_tests(test_request_data)
# print(run_result)
