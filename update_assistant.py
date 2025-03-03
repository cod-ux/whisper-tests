import requests

# Update Assistant (PATCH /assistant/:id)
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
          "content": "Pretend that you are Sarah, someone who wants to order a donut. If someone calls you then immediately start acting like you want to order a donut."
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
      "url": "https://2587-194-80-232-36.ngrok-free.app/vapi-webhook"
    }
  },
)

print(response.json())