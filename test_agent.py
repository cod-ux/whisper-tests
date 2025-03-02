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
import os, sys, json

# Set up logging
logging.basicConfig(
    level=logging.DEBUG,
    stream=sys.stderr,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv(override=True)

print("Starting subprocess")

TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER")


def serialize_test_results(test_result):
    """Convert TestResult objet to JSON-serializable python dict"""
    return {
        "test": {
            "scenario": {
                "name": test_result.test.scenario.name,
                "prompt": test_result.test.scenario.prompt,
                "evaluations": [
                    {"name": eval.name, "prompt": eval.prompt}
                    for eval in test_result.test.scenario.evaluations
                ],
            },
            "agent": {
                "name": test_result.test.agent.name,
                "prompt": test_result.test.agent.prompt,
                "voice_id": test_result.test.agent.voice_id,
            },
        },
        "evaluation_results": (
            {
                "evaluation_results": (
                    [
                        {
                            "name": eval.name,
                            "passed": eval.result.passed if eval.result else False,
                            "reason": (
                                eval.result.reason if eval.result else "Unknown reason"
                            ),
                        }
                        for eval in test_result.test.scenario.evaluations
                    ]
                    if test_result.evaluation_results
                    else []
                ),
                "extra_data": (
                    test_result.evaluation_results.extra_data
                    if test_result.evaluation_results
                    else {}
                ),
            }
            if test_result.evaluation_results
            else None
        ),
        "transcript": test_result.transcript,
        "stereo_recording_url": test_result.stereo_recording_url,
        "error": test_result.error,
    }


async def run_tests(main_data):
    logger.info("Request received at /runTests")
    print("Request received at /runTests")

    try:
        # Validate data
        if not isinstance(main_data, dict):
            return {"error": "Invalid input: expected dictionary"}

        if not main_data.get("tests"):
            return {"error": "No tests provided"}

        agent_type = main_data.get("agent_type")
        if not agent_type:
            return {"error": "agent_type is required"}

        phone_number = main_data.get("phone_number")
        if agent_type == "inbound" and not phone_number:
            return {"error": "Phone number is required for inbound agent"}

        # Setup ngrok
        port = 8765

        logger.info(f"Setting up ngrok on port {port}")
        try:
            listener = await ngrok.forward(
                port, authtoken=os.getenv("NGROK_AUTH_TOKEN")
            )
        except Exception as e:
            logger.error(f"Failed to setup ngrok: {str(e)}")
            return {"error": f"Failed to setup ngrok: {str(e)}"}

        # Load tests
        loaded_tests = []
        try:
            for test in main_data["tests"]:
                agent = Agent(name=test["agent_name"], prompt=test["agent_description"])
                scenario = Scenario(
                    name=test["scenario_name"],
                    prompt=test["scenario_description"],
                    evaluations=[
                        Evaluation(
                            name=e["eval_name"], prompt=e["eval_success_criteria"]
                        )
                        for e in test["evaluations"]
                    ],
                )
                loaded_tests.append(Test(agent=agent, scenario=scenario))
        except KeyError as e:
            logger.error(f"Missing required field in test data: {str(e)}")
            return {"error": f"Missing required field in test data: {str(e)}"}
        except Exception as e:
            logger.error(f"Failed to load tests: {str(e)}")
            return {"error": f"Failed to load tests: {str(e)}"}

        if not loaded_tests:
            return {"error": "No valid tests were loaded"}

        # Create test runner
        try:
            test_runner = TestRunner(
                port=port,
                ngrok_url=listener.url(),
                twilio_phone_number=TWILIO_PHONE_NUMBER,
                evaluator=LocalEvaluator(model="gpt-4o"),
            )
        except Exception as e:
            logger.error(f"Failed to create test runner: {str(e)}")
            return {"error": f"Failed to create test runner: {str(e)}"}

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
                return {"error": "Unsupported agent type"}

            if not test_results:
                return {"error": "Test results were empty"}

            logger.info("Tests completed successfully")
            serialized_results = [
                serialize_test_results(test_result) for test_result in test_results
            ]
            return {"output": serialized_results}

        except Exception as e:
            logger.error(f"Error running tests: {str(e)}", exc_info=True)
            return {"error": f"Error running tests: {str(e)}"}

    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}", exc_info=True)
        return {"error": f"Unexpected error: {str(e)}"}


if __name__ == "__main__":
    try:
        raw_input = sys.stdin.read()
        if not raw_input:
            print(json.dumps({"error": "No input received"}), flush=True)
            sys.exit(1)

        main_data = json.loads(raw_input)
        output = asyncio.run(run_tests(main_data))
        print(json.dumps(output), flush=True)
    except json.JSONDecodeError as e:
        print(json.dumps({"error": f"Invalid JSON input: {str(e)}"}), flush=True)
    except Exception as e:
        print(json.dumps({"error": f"Failed to process input: {str(e)}"}), flush=True)
