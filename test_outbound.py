import sys
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
import ngrok, uvicorn, os
from dotenv import load_dotenv
import logging
import asyncio
import requests, json
from openai import OpenAI
from pydantic import BaseModel


class EvalResult(BaseModel):
  name: str
  passed: bool
  reason: str

class EvalResults(BaseModel):
  evaluation_results: list[EvalResult]

# Configure logging immediately
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),  # Log to stdout instead of stderr
        logging.FileHandler("server.log", mode='w')  # Overwrite log file each run
    ]
)
logger = logging.getLogger(__name__)
logger.info("Script starting...")

load_dotenv(override=True)
logger.info("Environment loaded")

app = FastAPI()
client = OpenAI()
port = 8765

print("Starting subprocess...")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

shutdown_event = asyncio.Event()
received_data = {}

# Test webhook:
# Global variables
received_data = {}
shutdown_event = asyncio.Event()

def eval_and_serialize_call_data(req_data, call_data):
    """Evaluate and serialize call data processing"""
    logger.info("Evaluating call data...")

    messages = call_data["end-report"]["message"]["artifact"]["messagesOpenAIFormatted"][1:] #ignoring system message

    messages = [{"role": "user" if message["role"] == "assistant" else "AI", "content": message["content"]} for message in messages]
    formatted_messages = str(messages)

    evaluations = str(req_data["tests"][0]["evaluations"])

    prompt = f"""
    You are an expert at evaluating phone calls conducted by AI. You will be given a transcript of a call between an AI and a user, along with evaluation criteria to evaluate if the AI passed each of the evaluation criteria.

    Here is the transcrpt of the call:
    {formatted_messages}

    Please evaluate if the AI passed each of the evaluation criteria in the provided list:
    {evaluations}

    For each evaluation result, return the eval_name, passed status, and reason for the evaluation.
    """

    logger.info("Parsing evaluation prompt...")
    completion  = client.beta.chat.completions.parse(
      model="gpt-4o",
      messages=[
        {
          "role": "user",
          "content": prompt
        }
      ],
      response_format=EvalResults
    )

    evaluation_results = completion.choices[0].message.parsed

    logger.info("Evaluation results: %s", evaluation_results)

    # Convert to list format expected by TestResultsResponse
    return [{
        "test": {
            "scenario": {
                "name": req_data["tests"][0]["scenario_name"],
                "prompt": req_data["tests"][0]["scenario_description"],
                "evaluations": [
                    {"name": eval["eval_name"], "prompt": eval["eval_success_criteria"]}
                    for eval in req_data["tests"][0]["evaluations"]
                ],
            },
            "agent": {
                "name": req_data["tests"][0]["agent_name"], 
                "prompt": req_data["tests"][0]["agent_description"], 
                "voice_id": "",
            },
        },
        "evaluation_results": {
            "evaluation_results": [
                {
                    "name": eval.name,
                    "passed": eval.passed,
                    "reason": eval.reason
                }
                for eval in evaluation_results.evaluation_results
            ] if evaluation_results and hasattr(evaluation_results, 'evaluation_results') else [],
            "extra_data": {}
        },
        "transcript": messages,
        "stereo_recording_url": call_data["end-report"]["message"]["artifact"].get("stereoRecordingUrl", ""),
        "error": None
    }]

@app.post("/vapi-webhook")
async def vapi_webhook(request: Request):
  global received_data, main_data
  logger.info("Webhook endpoint called")
  # return response:

  payload = await request.json()
  try:
    if "message" in payload and "type" in payload["message"]:
      logger.info("[Debug] Received message")
      if payload["message"]["type"] == "end-of-call-report":
        logger.info("[Debug] Received message -> end of call report")
        if "customer" in payload["message"]:
          logger.info("[Debug] Customer field present")
          if "number" in payload["message"]["customer"]:
            logger.info("[Debug] Number present in customer field")
            if payload["message"]["customer"]["number"] == main_data["phone_number"]:
              logger.info("[Debug] Number in customer field matches main_data phone number")
              received_data["end-report"] = payload
              logger.info("[Debug] Setting shutdown event")
              shutdown_event.set()
      else:
        logger.info("Ignoring payload, not the correct end of report")

  except Exception as e:
    logger.error(f"Error: {e}")

async def update_assistant(req_data):
  
  agent_name = req_data["tests"][0]["agent_name"]
  agent_description = req_data["tests"][0]["agent_description"]
  scenario_name = req_data["tests"][0]["scenario_name"]
  scenario_description = req_data["tests"][0]["scenario_description"]

  formatted_content = f"""
  Your Name is {agent_name}. {agent_description}.

  Your task is to simulate this scenario immediately as soon as the conversation starts.
  Scenario Name: {scenario_name}
  Scenario Description: {scenario_description}
  """

  response = requests.patch(
    "https://api.vapi.ai/assistant/d9218669-4f7c-428c-9ff3-18ecabfd91c6",
    headers={
      "Authorization": "Bearer 1b84201e-91d7-4505-a34e-2b79e03d575b",
      "Content-Type": "application/json"
    },
    json={
      "model": {
        "provider": "openai",
        "model": "gpt-4o-mini",
        "messages": [
          {
            "role": "system",
            "content": formatted_content
          }
        ]
      },
      "firstMessage": "Hello",
      "firstMessageMode": "assistant-speaks-first",
      "analysisPlan": {
        "successEvaluationPlan": {
          "enabled": False
        }
      },
      "serverMessages": [
        "status-update",
        "end-of-call-report"
      ],
      "server": {
        "url": "https://728f-194-80-232-36.ngrok-free.app/vapi-webhook"
      }
    },
  )

  logger.info(response.json())
  return response.json()

async def run_tests(main_data):
  config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="info")
  server = uvicorn.Server(config)

  response = await update_assistant(main_data)

  if "statusCode" in response and response["statusCode"] != 200:
    logger.error(f"Failed to update assistant: {response['error']}")
    return {"error": f"Failed to update assistant: {response['error']}"}

  server_task = asyncio.create_task(server.serve())
  await shutdown_event.wait()
  logger.info("Shutting down server")
  server.should_exit = True
  await server_task

  results = eval_and_serialize_call_data(req_data=main_data, call_data=received_data)


  return results

if __name__ == "__main__":
    logger.info("Main block starting")
    try:
        raw_input = sys.stdin.read()
        logger.info("Test data loaded")
        
        if not raw_input:
            error_msg = "[Subprocess] No input received"
            logger.error(error_msg)
            print(json.dumps({"error": error_msg}), flush=True)
            sys.exit(1)

        global main_data
        main_data = json.loads(raw_input)
        logger.info(f"Parsed main_data with phone number: {main_data.get('phone_number')}")
        
        logger.info("Starting test execution")
        result = asyncio.run(run_tests(main_data))
        logger.info(f"Test execution completed with result")
        
        print(json.dumps({"output": result}), flush=True)

    except json.JSONDecodeError as e:
      print(json.dumps({"error": f"[Subprocess] Invalid JSON input: {str(e)}"}), flush=True)
      sys.exit(1)

    except Exception as e:
      print(json.dumps({"error": f"[Subprocess] Failed to process input: {str(e)}"}), flush=True)
      sys.exit(1)
  
  