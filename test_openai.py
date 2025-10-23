import os
from dotenv import load_dotenv

load_dotenv()

print("Testing OpenAI import...")
from openai import OpenAI

print("Creating client...")
print(f"API Key exists: {bool(os.getenv('OPENAI_API_KEY'))}")

try:
    client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
    print("SUCCESS! Client created")
    
    # Try a simple call
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": "say hello"}],
        max_tokens=10
    )
    print(f"Response: {response.choices[0].message.content}")
    
except Exception as e:
    import traceback
    print("\nFULL ERROR:")
    traceback.print_exc()