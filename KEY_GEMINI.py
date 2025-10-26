from google import genai

client= genai.Client()
response= client.generate_text(
    model="gemini-2.5-flash", content="Hello, world!")
print