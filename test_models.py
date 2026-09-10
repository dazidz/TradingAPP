from groq import Groq

# Nutzt direkt den Key aus deinen Streamlit Secrets oder trage ihn hier kurz ein
client = Groq(api_key="os.getenv("GROQ_API_KEY")")

print("Verfügbare Modelle:")
models = client.models.list()
for model in models.data:
  print(f"- {model.id}")